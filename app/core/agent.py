
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
from app.services.db.mongo_utils import return_system_prompt
from app.services.db.chroma.utils import upsert_data, fetch_data, upsert_kb, fetch_kb, fetch_journal
from app.services.db.chat_session_utils import (
    create_chat_session,
    get_chat_session,
    get_session_messages,
    add_session_message,
    set_session_title,
    list_chat_sessions,
)
from app.services.db.journal_utils import get_journal_logs
from app.utils.logger_config import logger
import json
import time

from app.utils.env_load import openai_api_key
from app.core.agent_utils import (
    system_prompt,
    tools,
    FEATURE_DEFAULT_LABELS,
    TOOL_GROUNDING_INSTRUCTIONS,
    APP_FEATURE_REFERRAL_INSTRUCTIONS,
    KB_USAGE_INSTRUCTIONS,
    RESPONSE_STYLE_INSTRUCTIONS,
    OPENING_MESSAGE_INSTRUCTIONS,
)

openai_client = OpenAI(
    api_key=openai_api_key
)

_title_executor = ThreadPoolExecutor(max_workers=2)
# Tool reads within a single model turn are independent (each is an embedding call + a Pinecone
# query), so they run concurrently instead of serially — a 3-tool turn costs one tool's latency.
_tool_executor = ThreadPoolExecutor(max_workers=8)
# Separate pool for fire-and-forget writes, so a burst of them can't starve the reads above.
_bg_executor = ThreadPoolExecutor(max_workers=4)

# The persona prompt lives in Mongo but changes rarely, while it's read on every single request.
_SYSTEM_PROMPT_TTL_SECONDS = 300
_system_prompt_cache = {"value": None, "fetched_at": 0.0}


def _get_cached_system_prompt() -> str:
    now = time.monotonic()
    if (
        _system_prompt_cache["value"] is not None
        and now - _system_prompt_cache["fetched_at"] < _SYSTEM_PROMPT_TTL_SECONDS
    ):
        return _system_prompt_cache["value"]

    try:
        prompt = return_system_prompt()
        value = prompt.get("prompt", system_prompt) if prompt else system_prompt
    except Exception as e:
        # A slow/failing Mongo read must not take the chat down — fall back to the bundled persona.
        logger.warning("Failed to load system prompt, using fallback", extra={"error": str(e)})
        value = _system_prompt_cache["value"] or system_prompt

    _system_prompt_cache["value"] = value
    _system_prompt_cache["fetched_at"] = now
    return value


# Messages that carry no new topic to ground against — the reply lives entirely in what was just
# said. Deliberately a closed set rather than a heuristic: a false positive here silently costs
# grounding, which is the failure mode we're fixing, so anything not on this list counts as
# substantive. Skipping the prefetch still leaves all four tools available to the model.
_LOW_SIGNAL_MESSAGES = {
    "", "hi", "hey", "hello", "yo", "hiya",
    "ok", "okay", "k", "kk", "sure", "fine", "alright",
    "yes", "yeah", "yep", "yup", "no", "nope", "nah",
    "thanks", "thank you", "ty", "thankyou", "thanks so much", "thank you so much",
    "cool", "nice", "great", "amazing", "perfect", "lovely", "wow", "omg",
    "love it", "love this", "got it", "makes sense", "that makes sense", "i see",
    "tell me more", "more", "go on", "continue", "and", "so",
    "please", "haha", "lol", "hmm", "hm", "true", "right", "exactly", "same",
}
_LOW_SIGNAL_MAX_WORDS = 6

# Words that carry no topic on their own, so a message built only from them ("ok cool", "yeah
# thanks", "oh nice") is filler however they're combined — the exact-phrase set above can't
# enumerate every pairing. Deliberately excludes "i", "me", "you" and "love": "i love you" and
# "you hurt me" are made of small words but are the most substantive things someone could say.
_LOW_SIGNAL_WORDS = {
    "hi", "hey", "hello", "yo", "hiya", "oh", "ah", "aw", "yay",
    "ok", "okay", "k", "kk", "sure", "fine", "alright", "cool", "nice", "great",
    "amazing", "perfect", "lovely", "wow", "omg", "good", "sweet", "awesome",
    "yes", "yeah", "yep", "yup", "no", "nope", "nah", "thanks", "ty",
    "got", "it", "this", "that", "makes", "sense", "true", "right", "exactly",
    "same", "haha", "lol", "hmm", "hm", "please", "and", "so", "very", "really",
    "just", "much", "totally", "definitely", "for", "now", "then", "well",
}

# Polite multi-word forms collapsed before the word check, so "you" can stay out of the vocab.
_POLITE_FORMS = [
    ("thank you so much", "thanks"), ("thanks so much", "thanks"),
    ("thank you very much", "thanks"), ("thank you", "thanks"), ("thankyou", "thanks"),
]


def _is_low_signal(message: str) -> bool:
    """True if the message is pure acknowledgement / small talk with no topic to retrieve on."""
    normalized = "".join(c for c in message.lower() if c.isalnum() or c.isspace())
    normalized = " ".join(normalized.split())

    # Emoji- or punctuation-only messages normalize to empty.
    if not normalized:
        return True
    for form, replacement in _POLITE_FORMS:
        normalized = normalized.replace(form, replacement)
    normalized = " ".join(normalized.split())

    words = normalized.split()
    # Anything with real length is substantive by definition — never gamble on it.
    if len(words) > _LOW_SIGNAL_MAX_WORDS:
        return False
    if normalized in _LOW_SIGNAL_MESSAGES:
        return True
    return all(w in _LOW_SIGNAL_WORDS for w in words)


def _prefetch_user_context(email: str, message: str) -> str:
    """Fetch long-term memory + journal context up front, in parallel.

    Runs on the opening turn and on every substantive turn after it. Grounding used to be left to
    the model deciding to call these two tools, which cost a full model round-trip when it did and
    silently lost grounding when it didn't. Retrieving directly is both cheaper (one Pinecone hop,
    no model hop) and reliable. Only genuine filler turns skip it — see _is_low_signal.
    """
    futures = {
        "memory": _tool_executor.submit(get_memory, email, message),
        "journal": _tool_executor.submit(get_journal_context, email, message),
    }
    resolved = {}
    for label, future in futures.items():
        try:
            resolved[label] = future.result(timeout=8)
        except Exception as e:
            # Opening context is a bonus, not a requirement — a slow or failing lookup should
            # degrade to "no context" rather than delay or break the first reply.
            logger.warning("Context prefetch failed", extra={"email": email, "source": label, "error": str(e)})
            resolved[label] = {}

    memory = (resolved["memory"].get("long_term_memory") or "").strip()
    journal = (resolved["journal"].get("journal_context") or "").strip()

    parts = []
    if memory:
        parts.append(f"What you remember about them:\n{memory}")
    if journal:
        parts.append(f"Their recent journal entries:\n{journal}")

    if not parts:
        # Say so explicitly, otherwise the model burns a round-trip fetching these itself.
        return (
            "CONTEXT FOR THIS TURN: nothing stored in their memory or journal matches this topic. Do "
            "not call get_memory or get_journal_context this turn — they have already been checked "
            "and there is nothing to find. Ground your reply in what they just said, and in the "
            "knowledge base if you're teaching them anything."
        )

    return (
        "CONTEXT FOR THIS TURN (already retrieved for you — do not call get_memory or "
        "get_journal_context again this turn):\n\n" + "\n\n".join(parts)
    )


def _run_tool(email: str, func_name: str, func_args: dict):
    """Execute one tool call. Returns (content_for_model, kb_reference, cta).

    kb_reference is None for every tool except search_knowledge_base, where it's a
    single {"query": ..., "chunks": [...]} record — the query that was searched
    paired with exactly what came back, for kb_references on the stored message.

    cta is None for every tool except show_feature_cta, where it's a
    {"feature": ..., "label": ..., "reason": ...} record for the frontend to render
    as a button — no URL, the frontend already owns its own route per feature.
    """
    if func_name == "search_knowledge_base":
        query = func_args["query"]
        context, chunks = get_kb_context(query)
        reference = {"query": query, "chunks": chunks} if chunks else None
        return json.dumps({"knowledge_base": context}), reference, None

    if func_name == "get_memory":
        return json.dumps(get_memory(email, func_args["memory"])), None, None

    if func_name == "update_memory":
        # Fire-and-forget: the model never reads anything back from a write, so making it wait on
        # an embedding call plus a Pinecone upsert is pure added latency on the user's reply.
        _bg_executor.submit(update_memory, email, func_args["memory"])
        return f"Memory stored successfully: {func_args['memory']}", None, None

    if func_name == "get_journal_context":
        return json.dumps(get_journal_context(email, func_args["query"])), None, None

    if func_name == "show_feature_cta":
        feature = func_args["feature"]
        if feature not in FEATURE_DEFAULT_LABELS:
            return json.dumps({"error": f"Unknown feature '{feature}'"}), None, None
        cta = {
            "feature": feature,
            "label": func_args.get("cta_text") or FEATURE_DEFAULT_LABELS[feature],
            "reason": func_args.get("reason", ""),
        }
        return json.dumps({"status": "shown"}), None, cta

    logger.warning("Unknown tool called", extra={"email": email, "tool": func_name})
    return json.dumps({"error": f"Unknown tool '{func_name}'"}), None, None


def _generate_and_set_title(session_id: str, email: str, user_message: str, assistant_reply: str) -> None:
    try:
        response = openai_client.responses.create(
            model="gpt-4.1-nano",
            instructions=(
                "Generate a short session title (4-6 words max) that captures the core topic "
                "of this wellness conversation. No quotes, no punctuation at the end. "
                "Examples: 'Work Stress and Burnout', 'Anxiety Around Relationships', "
                "'Letting Go of Grief', 'Finding Inner Confidence'."
            ),
            input=[
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_reply},
            ],
            max_output_tokens=20,
            temperature=0.5,
        )
        title = response.output_text.strip().strip('"').strip("'")
        set_session_title(session_id=session_id, email=email, title=title)
        logger.info("Session title generated", extra={"session_id": session_id, "title": title})
    except Exception as e:
        logger.warning("Failed to generate session title, falling back to message", extra={"error": str(e)})
        set_session_title(session_id=session_id, email=email, title=user_message)


def get_embedding(text:str):
    response = openai_client.embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )

    return response.data[0].embedding


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Batch-embed multiple texts in a single OpenAI call."""
    response = openai_client.embeddings.create(
        input=texts,
        model="text-embedding-3-small"
    )
    return [item.embedding for item in response.data]

def update_memory(user: str, memory: str):
    try:
        logger.info("Updating long-term memory", extra={"user": user, "memory": memory})
        embedding = get_embedding(memory)
        upsert_data(
            user_id=user,
            vector=embedding,
            text=memory
        )
        logger.info("Memory updated successfully", extra={"user": user})
    except Exception as e:
        logger.error("[update_memory] Error", extra={"user": user, "error": str(e)})
        raise e


def get_memory(user: str, memory: str):
    try:
        logger.info("Fetching long-term memory", extra={"user": user, "query": memory})
        embedding = get_embedding(memory)
        results = fetch_data(
            user_id=user,
            vector=embedding
        )
        value = []
        for match in results:
            text = (match.get("metadata", {}).get("text") or "").strip()
            if text:
                value.append(text)
        logger.info("Memory fetched", extra={"user": user, "results_count": len(value)})
        return {"long_term_memory": "\n".join(value)}

    except Exception as e:
        logger.error("[get_memory] Error", extra={"user": user, "error": str(e)})
        raise e


def get_journal_context(user: str, query: str):
    try:
        logger.info("Fetching journal context", extra={"user": user, "query": query})
        embedding = get_embedding(query)
        results = fetch_journal(email=user, vector=embedding, top_k=3)
        value = []
        for match in results:
            text = (match.get("metadata", {}).get("text") or "").strip()
            if text:
                value.append(text)
        logger.info("Journal context fetched", extra={"user": user, "results_count": len(value)})
        return {"journal_context": "\n".join(value)}
    except Exception as e:
        logger.error("[get_journal_context] Error", extra={"user": user, "error": str(e)})
        raise e


KB_CHUNK_SEPARATOR = "\n\n---\n\n"


def get_kb_context(query: str, k: int = 5):
    """Retrieve top-k relevant KB chunks, labeled by source section.

    Each chunk is now a complete, self-contained "## [PREFIX-NN] Title" teaching
    (see scripts/ingest_kb_markdown.py) spanning multiple paragraphs, not the old
    single-line ~1200-char slice from chunk_text() — so chunks are joined with a
    clear separator (never a bare "\\n", which the old chunk text never contained
    but section text does) and labeled with their section_title so the model can
    tell where one teaching ends and the next begins.

    k defaults higher than before (5, was 3): the KB is now several companion
    documents sharing one collection (journaling, money mindset, nervous-system/
    boundaries work) rather than a single PDF, so a query has more ground to cover.

    Returns (context_text_for_model, chunk_records). chunk_records is one dict per
    matched chunk — {id, section_title, doc_title, text} — a full record of what
    was actually retrieved, for kb_references (not for splitting context_text).
    """
    try:
        embedding = get_embedding(query)
        results = fetch_kb(
            vector=embedding,
            top_k=k
        )

        blocks = []
        chunk_records = []
        for match in results:
            metadata = match.get("metadata", {})
            text = (metadata.get("text") or "").strip()
            if not text:
                continue
            section_title = metadata.get("section_title")
            doc_title = metadata.get("doc_title")
            label = section_title or doc_title
            blocks.append(f"[{label}]\n{text}" if label else text)
            chunk_records.append({
                "id": match.get("id", ""),
                "section_title": section_title,
                "doc_title": doc_title,
                "text": text,
            })

        logger.info("KB context fetched", extra={"query": query, "chunks": len(blocks)})
        return KB_CHUNK_SEPARATOR.join(blocks), chunk_records
    except Exception as e:
        logger.error("[get_kb_context] Error", extra={"query": query, "error": str(e)})
        return "", []

def update_kb(doc_id: str, text: str):
    """Insert/update therapist knowledge docs into KB vector DB"""
    try:
        logger.info("Upserting KB document", extra={"doc_id": doc_id})
        embedding = get_embedding(text)
        upsert_kb(
            doc_id=doc_id,
            vector=embedding,
            text=text
        )
        logger.info("KB document upserted", extra={"doc_id": doc_id})
    except Exception as e:
        logger.error("[update_kb] Error", extra={"doc_id": doc_id, "error": str(e)})
        raise e

ICE_BREAKER_PROMPT = """You are Sanaya AI, a warm manifestation and wellness coach.

Generate exactly 4 ultra-short conversation-starter chips a user can tap to begin a session.
Think of them as button labels — brief, punchy, and instantly relatable.

Rules:
- Max 5 words each. No exceptions.
- Write in first person fragments ("Feeling stuck lately", "My morning routine", "Fear of being seen")
- No full sentences, no punctuation at the end
- Use context provided (moods, themes, people, recent topics) to make them feel personal
- If no context, use universal wellness/manifestation themes
- Vary the angle: one emotion, one goal/block, one relationship/situation, one growth
- Return ONLY valid JSON, no text outside:
{
  "starters": ["...", "...", "...", "..."]
}"""


def generate_ice_breakers(email: str, username: str = "") -> dict:
    email = email.lower()
    logger.info("Generating ice breakers", extra={"email": email})

    try:
        context_parts = []

        # Pull themes/moods from recent journals
        recent_logs = get_journal_logs(email, limit=3)
        if recent_logs:
            journal_lines = []
            for log in recent_logs:
                journal_lines.append(
                    f"- mood: {log.get('mood', '')}, theme: {log.get('theme', '')}, "
                    f"people: {', '.join(log.get('people', []))}"
                )
            context_parts.append("Recent journal entries:\n" + "\n".join(journal_lines))

        # Pull title of most recent chat session as a topic hint
        sessions = list_chat_sessions(email)
        if sessions:
            recent_titles = [s["title"] for s in sessions[:3] if s.get("title") and s["title"] != "New Chat"]
            if recent_titles:
                context_parts.append("Recent chat topics: " + " | ".join(recent_titles))

        if username:
            context_parts.insert(0, f"User's name: {username}")

        user_content = "\n\n".join(context_parts) if context_parts else "No prior context available."

        response = openai_client.responses.create(
            model="gpt-4.1-mini",
            instructions=ICE_BREAKER_PROMPT,
            input=[
                {"role": "user", "content": user_content},
            ],
            temperature=0.9,
            # Schema-enforced JSON instead of trusting the prompt's "return only valid JSON" —
            # guarantees a parseable {"starters": [...]}. shape rather than hoping for one.
            text={
                "format": {
                    "type": "json_schema",
                    "name": "ice_breakers",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "starters": {"type": "array", "items": {"type": "string"}}
                        },
                        "required": ["starters"],
                        "additionalProperties": False
                    },
                    "strict": True
                }
            },
        )

        result = json.loads(response.output_text)
        starters = result.get("starters", [])

        logger.info("Ice breakers generated", extra={"email": email, "count": len(starters)})
        return {"success": True, "starters": starters}

    except json.JSONDecodeError as e:
        logger.error("[generate_ice_breakers] JSON parse error", extra={"email": email, "error": str(e)})
        return {"success": False, "message": "Failed to generate starters."}
    except Exception as e:
        logger.error("[generate_ice_breakers] Error", extra={"email": email, "error": str(e)})
        return {"success": False, "message": "Something went wrong. Please try again later."}


MAX_TOOL_ITERATIONS = 5


def chat_agent(email: str, message: str, session_id: str = None, username: str = "", source: str = "direct"):
    email = email.lower()
    logger.info("Chat agent invoked", extra={"email": email, "session_id": session_id})

    mmd_system_prompt = _get_cached_system_prompt()

    try:
        # Create a new session if none provided
        if not session_id:
            session_id = create_chat_session(email, source=source)
            logger.info("New chat session created", extra={"email": email, "session_id": session_id})
        else:
            session = get_chat_session(session_id=session_id, email=email)
            if not session:
                return {"success": False, "message": "Session not found."}

        history = get_session_messages(session_id=session_id, email=email, limit=20)
        # Strip timestamps before sending to the model
        history_for_model = [{"role": m["role"], "content": m["content"]} for m in history]

        # Nothing in the profile records gender, while the persona prompt refers to the user as
        # "she"/"her" throughout — so without this the model addresses every user as a woman.
        user_context = (
            (f"The user's name is {username}. " if username else "")
            + "You do not know this user's gender, and a name is not evidence of it. Refer to them "
            "with neutral language (they/them) unless they tell you otherwise — this holds even "
            "where the instructions above are written as \"she\" or \"her\"."
        )
        messages = [
            # mmd_system_prompt is passed via the top-level `instructions` param below, not as an
            # input item — that's what it's for in the Responses API.
            {"role": "system", "content": TOOL_GROUNDING_INSTRUCTIONS},
            {"role": "system", "content": APP_FEATURE_REFERRAL_INSTRUCTIONS},
            {"role": "system", "content": KB_USAGE_INSTRUCTIONS},
            # Last of the system messages on purpose: it overrides the persona prompt's multi-step
            # reply structure, so it should be the closest one to the user turn.
            {"role": "system", "content": RESPONSE_STYLE_INSTRUCTIONS},
            {"role": "system", "content": user_context.strip()},
            *history_for_model,
        ]

        # Static text, so it stays in the cached prefix — but only relevant (and only included) on
        # the opening turn, where MATCH THEIR WEIGHT's "one-line, no pattern" default would otherwise
        # suppress exactly the memory/journal callback _prefetch_user_context just fetched for it.
        if not history:
            messages.append({"role": "system", "content": OPENING_MESSAGE_INSTRUCTIONS})

        # Ground every substantive turn, and always the opening one — "hi" on turn 1 is exactly when
        # greeting them by what you remember matters. Only mid-conversation filler skips the lookup.
        # Appended here rather than up with the system messages on purpose: this text differs on
        # every request, so keeping it out of the cached prefix protects the prompt cache, and
        # sitting next to their message is where it's most likely to be used.
        if not history or not _is_low_signal(message):
            messages.append({"role": "system", "content": _prefetch_user_context(email, message)})
        else:
            logger.info("Skipped context prefetch (low-signal turn)", extra={"email": email, "session_id": session_id})

        messages.append({"role": "user", "content": message})

        reply = None
        kb_references = []
        cta = None
        for iteration in range(MAX_TOOL_ITERATIONS):
            response = openai_client.responses.create(
                model="gpt-5-mini",
                instructions=mmd_system_prompt,
                input=messages,
                tools=tools,
                tool_choice="auto",
                temperature=1.0,
                # gpt-5-mini is a reasoning model and defaults to medium effort, which it pays on
                # every hop of the tool loop. This is a chat persona doing retrieval, not a hard
                # reasoning task — "low" cuts several seconds per hop.
                reasoning={"effort": "low"},
                # Stable key so the long system-prompt prefix keeps hitting the same prompt cache.
                prompt_cache_key="sanaya-chat-v1",
            )

            function_calls = [item for item in response.output if item.type == "function_call"]

            if not function_calls:
                reply = response.output_text
                break

            # Echo back everything the model produced this hop (function calls, and any reasoning
            # items alongside them) — the Responses API is stateless per-call, so the next hop only
            # has the reasoning context behind these calls if we hand the full output back to it.
            messages.extend(response.output)

            # Dispatch all of this hop's tools at once, then collect in the original order so each
            # call_id still lines up with its result.
            futures = []
            for fc in function_calls:
                func_name = fc.name
                func_args = json.loads(fc.arguments)
                logger.info("Tool call triggered", extra={"email": email, "tool": func_name, "iteration": iteration})
                futures.append((fc, _tool_executor.submit(_run_tool, email, func_name, func_args)))

            for fc, future in futures:
                try:
                    tool_result_content, reference, tool_cta = future.result()
                    if reference:
                        kb_references.append(reference)
                    if tool_cta:
                        cta = tool_cta
                except Exception as e:
                    # One failed retrieval shouldn't kill the whole reply — tell the model and
                    # let it answer with what it does have.
                    logger.error(
                        "[chat_agent] Tool execution failed",
                        extra={"email": email, "tool": fc.name, "error": str(e)},
                    )
                    tool_result_content = json.dumps({"error": "Lookup failed, no data available."})

                messages.append({
                    "type": "function_call_output",
                    "call_id": fc.call_id,
                    "output": tool_result_content
                })

        if not reply:
            logger.warning("Agent loop exhausted without reply", extra={"email": email})
            reply = "I'm here with you. Could you share a little more about what you mean?"

        add_session_message(session_id=session_id, email=email, role="user", content=message)
        add_session_message(
            session_id=session_id,
            email=email,
            role="assistant",
            content=reply,
            kb_references=kb_references or None,
            cta=cta,
        )

        if len(history) == 2:
            _title_executor.submit(_generate_and_set_title, session_id=session_id, email=email, user_message=message, assistant_reply=reply)

        logger.info("Reply generated", extra={"email": email, "session_id": session_id})
        return {"success": True, "reply": reply, "session_id": session_id, "cta": cta}

    except Exception as e:
        logger.error("[chat_agent] Error", extra={"email": email, "error": str(e)})
        return {
            "success": False,
            "message": "Something went wrong. Please try again later."
        }
