import io
import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI
from elevenlabs.client import ElevenLabs
from pydub import AudioSegment

from app.core.eft_agent.eft_agent_utils import (
    EFT_SYSTEM_PROMPT,
    EFT_TOOLS,
    TRANSLITERATION_SYSTEM_PROMPT,
)
from app.services.db.eft_utils import (
    create_eft_session,
    get_eft_session,
    add_session_message,
    get_session_messages,
    mark_session_complete,
)
from app.services.storage.r2_utils import upload_media
from app.utils.env_load import openai_api_key, elevenlabs_api_key
from app.utils.logger_config import logger
from app.services import event_bus
from app.services.gupshup.notifications import send_eft_ready_whatsapp

openai_client = OpenAI(api_key=openai_api_key)
elevenlabs_client = ElevenLabs(api_key=elevenlabs_api_key)

# aura — calm, warm voice well suited for guided tapping sessions
EFT_VOICE_ID = "hnMOqbQV1aV5iom08kJd"

MAX_TOOL_ITERATIONS = 3

# Any stray pause/XML markup the model emits is stripped — the voice would otherwise
# read it aloud or stutter on it. Pacing comes from the writing, not from tags.
BREAK_TAG_RE = re.compile(r"<[^>]{0,80}>")
PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")

# Well under the ElevenLabs per-request character limit, so a full 9–10 minute
# script is spoken in a handful of requests instead of one oversized one. Also keeps
# each transliteration request small enough that the model reliably respells the whole
# chunk instead of shortening it.
MAX_TTS_CHARS = 1500

DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")

# A faithful transliteration is close to the source in length. Anything much shorter means
# the model summarised or dropped text, so that chunk falls back to English.
MIN_TRANSLITERATION_RATIO = 0.6


def _transliterate_chunk(text: str) -> str:
    """Respell one English script chunk in Devanagari letters — same English words,
    phonetically written — so the Hindi TTS voice reads it with a natural Indian accent.
    Not a translation.

    One chunk per request: batching made the model merge segments, which failed the count
    check and dropped the entire script back to English. On any failure the original
    English text is returned, so a bad chunk costs only its own accent.
    """
    if not text.strip():
        return text

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": TRANSLITERATION_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps({"segments": [text]}, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        data = json.loads(response.choices[0].message.content)
        result = data.get("segments")

        if not isinstance(result, list) or not result:
            logger.warning("Transliteration returned no segment; using original English")
            return text

        # The model occasionally splits one input into several strings — joining them back
        # is correct here, since the whole chunk is one continuous passage.
        out = " ".join(str(seg) for seg in result).strip()

        if not DEVANAGARI_RE.search(out):
            logger.warning("Transliteration returned no Devanagari; using original English")
            return text

        if len(out) < len(text) * MIN_TRANSLITERATION_RATIO:
            logger.warning(
                "Transliteration suspiciously short; using original English",
                extra={"source_chars": len(text), "result_chars": len(out)},
            )
            return text

        return out
    except Exception as e:
        logger.error("Transliteration failed; using original English", extra={"error": str(e)})

    return text


def _chunk_script(script: str) -> list[str]:
    """Split the script into TTS-sized chunks on paragraph boundaries (falling back to
    sentence boundaries for any oversized paragraph), so the audio joins seamlessly."""
    script = BREAK_TAG_RE.sub("", script)

    pieces: list[str] = []
    for para in (p.strip() for p in PARAGRAPH_SPLIT_RE.split(script)):
        if not para:
            continue
        if len(para) <= MAX_TTS_CHARS:
            pieces.append(para)
            continue
        # Paragraph too long for one request — pack its sentences into chunks.
        current = ""
        for sentence in SENTENCE_SPLIT_RE.split(para):
            candidate = f"{current} {sentence}".strip()
            if current and len(candidate) > MAX_TTS_CHARS:
                pieces.append(current)
                current = sentence.strip()
            else:
                current = candidate
        if current:
            pieces.append(current)

    # Combine adjacent paragraphs while they still fit, to keep requests (and joins) few.
    chunks: list[str] = []
    for piece in pieces:
        if chunks and len(chunks[-1]) + len(piece) + 1 <= MAX_TTS_CHARS:
            chunks[-1] = f"{chunks[-1]} {piece}"
        else:
            chunks.append(piece)

    return chunks or ([script.strip()] if script.strip() else [])


def _elevenlabs_tts(text: str) -> bytes:
    audio_chunks = elevenlabs_client.text_to_speech.convert(
        voice_id=EFT_VOICE_ID,
        text=text,
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
    )
    return b"".join(audio_chunks)


def _speak_chunk(text: str) -> bytes:
    """Respell one chunk in Devanagari letters, then speak it."""
    return _elevenlabs_tts(_transliterate_chunk(text))


def _build_voice_audio(script: str) -> bytes:
    """Speak the script in TTS-sized chunks and join them back to back. Chunking keeps each
    request under the per-request character limit that a full 9–10 minute script would
    otherwise exceed; no silence is inserted, so the audio reads as one continuous take."""
    chunks = _chunk_script(script)
    if not chunks:
        raise ValueError("EFT script is empty")

    logger.info("Speaking EFT script in chunks", extra={"chunks": len(chunks), "chars": len(script)})

    tts_results: dict[int, bytes] = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_speak_chunk, text): i for i, text in enumerate(chunks)}
        for future in as_completed(futures):
            tts_results[futures[future]] = future.result()

    combined = AudioSegment.empty()
    for i in range(len(chunks)):
        combined += AudioSegment.from_mp3(io.BytesIO(tts_results[i]))

    out = io.BytesIO()
    combined.export(out, format="mp3", bitrate="128k")
    return out.getvalue()


def _generate_and_store_audio(email: str, session_id: str, script: str) -> str:
    """Convert script to speech via ElevenLabs and upload to R2. Returns public URL."""
    logger.info("Generating EFT audio via ElevenLabs", extra={"email": email, "session_id": session_id})

    audio_bytes = _build_voice_audio(script)
    key = f"eft_audio/{email}/{session_id}.mp3"
    url = upload_media(io.BytesIO(audio_bytes), key, content_type="audio/mpeg")

    logger.info("EFT audio stored in R2", extra={"email": email, "session_id": session_id, "url": url})
    return url


def eft_chat(email: str, message: str, session_id: str = None) -> dict:
    email = email.lower()
    logger.info("EFT chat invoked", extra={"email": email, "session_id": session_id})

    try:
        if not session_id:
            session_id = create_eft_session(email)
            logger.info("New EFT session created", extra={"email": email, "session_id": session_id})
        else:
            session = get_eft_session(session_id=session_id, email=email)
            if not session:
                return {"success": False, "message": "Session not found."}
            if session.get("is_complete"):
                return {
                    "success": True,
                    "session_id": session_id,
                    "reply": "This session has already been completed. Start a new one when you're ready.",
                    "is_complete": True,
                    "audio_url": session.get("audio_url"),
                }

        history = get_session_messages(session_id=session_id, email=email)

        messages = [
            {"role": "system", "content": EFT_SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": message},
        ]

        reply = None
        audio_url = None
        is_complete = False

        for iteration in range(MAX_TOOL_ITERATIONS):
            response = openai_client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages,
                tools=EFT_TOOLS,
                tool_choice="auto",
                temperature=1.0,
            )

            result = response.choices[0]

            if result.finish_reason != "tool_calls":
                reply = result.message.content
                break

            tool_call = result.message.tool_calls[0]
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments)

            logger.info("EFT tool call", extra={"email": email, "tool": func_name, "iteration": iteration})

            if func_name == "generate_eft_audio":
                script = func_args.get("script", "")
                try:
                    audio_url = _generate_and_store_audio(email, session_id, script)
                    mark_session_complete(session_id=session_id, audio_url=audio_url)
                    is_complete = True
                    event_bus.publish(email, {
                        "type": "eft_complete",
                        "title": "Your tapping session is ready",
                        "body": "Tap to listen.",
                        "data": {"session_id": session_id, "audio_url": audio_url, "url": "https://app.regulatewithaura.com/eft-tapping"},
                    })
                    send_eft_ready_whatsapp(email, session_id)
                    tool_result_content = json.dumps({"audio_url": audio_url, "success": True})
                except Exception as audio_err:
                    logger.error("EFT audio generation failed", extra={"email": email, "error": str(audio_err)})
                    tool_result_content = json.dumps({"success": False, "error": str(audio_err)})
            else:
                logger.warning("Unknown EFT tool called", extra={"email": email, "tool": func_name})
                break

            messages.append({
                "role": "assistant",
                "tool_calls": [{
                    "id": tool_call.id,
                    "type": "function",
                    "function": {"name": func_name, "arguments": json.dumps(func_args)},
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result_content,
            })

        if not reply:
            logger.warning("EFT agent loop exhausted without reply", extra={"email": email})
            reply = "I'm right here with you. Take a breath. What are you noticing?"

        add_session_message(session_id=session_id, role="user", content=message)
        add_session_message(session_id=session_id, role="assistant", content=reply)

        logger.info("EFT reply generated", extra={"email": email, "session_id": session_id, "is_complete": is_complete})

        return {
            "success": True,
            "session_id": session_id,
            "reply": reply,
            "is_complete": is_complete,
            "audio_url": audio_url,
        }

    except Exception as e:
        logger.error("[eft_chat] Error", extra={"email": email, "error": str(e)})
        return {"success": False, "message": "Something went wrong. Please try again."}
