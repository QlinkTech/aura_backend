
from openai import OpenAI
from app.services.db.mongo_utils import return_system_prompt
from app.services.db.pinecone_utils import upsert_data, fetch_data, upsert_kb, fetch_kb, fetch_journal
from app.services.db.chat_session_utils import (
    create_chat_session,
    get_chat_session,
    get_session_messages,
    add_session_message,
    set_session_title,
)
from app.utils.logger_config import logger
import json

from app.utils.env_load import openai_api_key
from app.core.agent_utils import system_prompt, tools

openai_client = OpenAI(
    api_key=openai_api_key
)

def get_embedding(text:str):
    response = openai_client.embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )

    return response.data[0].embedding

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
            if 'text' in match['metadata']:
                value.append(match['metadata']['text'])
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
            if "text" in match.get("metadata", {}):
                value.append(match["metadata"]["text"])
        logger.info("Journal context fetched", extra={"user": user, "results_count": len(value)})
        return {"journal_context": "\n".join(value)}
    except Exception as e:
        logger.error("[get_journal_context] Error", extra={"user": user, "error": str(e)})
        raise e


def get_kb_context(query: str, k: int = 3):
    """Retrieve top-k relevant knowledge docs"""
    try:
        embedding = get_embedding(query)
        results = fetch_kb(
            vector=embedding,
            top_k=k
        )
        context = []
        for match in results:
            if "text" in match["metadata"]:
                context.append(match["metadata"]["text"])
        logger.info("KB context fetched", extra={"query": query, "chunks": len(context)})
        return "\n".join(context)
    except Exception as e:
        logger.error("[get_kb_context] Error", extra={"query": query, "error": str(e)})
        return ""

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

MAX_TOOL_ITERATIONS = 5


def chat_agent(email: str, message: str, session_id: str = None, username: str = ""):
    email = email.lower()
    logger.info("Chat agent invoked", extra={"email": email, "session_id": session_id})

    prompt = return_system_prompt()
    mmd_system_prompt = prompt.get("prompt", system_prompt) if prompt else system_prompt

    try:
        # Create a new session if none provided
        if not session_id:
            session_id = create_chat_session(email)
            logger.info("New chat session created", extra={"email": email, "session_id": session_id})
        else:
            session = get_chat_session(session_id=session_id, email=email)
            if not session:
                return {"success": False, "message": "Session not found."}

        history = get_session_messages(session_id=session_id, email=email, limit=20)
        # Strip timestamps before sending to the model
        history_for_model = [{"role": m["role"], "content": m["content"]} for m in history]

        user_context = f"The user's name is {username}. " if username else ""
        messages = [
            {"role": "system", "content": mmd_system_prompt},
            {"role": "system", "content": user_context.strip()},
            *history_for_model,
            {"role": "user", "content": message},
        ]

        reply = None
        for iteration in range(MAX_TOOL_ITERATIONS):
            response = openai_client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=1.0
            )

            result = response.choices[0]

            if result.finish_reason != "tool_calls":
                reply = result.message.content
                break

            tool_call = result.message.tool_calls[0]
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments)

            logger.info("Tool call triggered", extra={"email": email, "tool": func_name, "iteration": iteration})

            if func_name == "search_knowledge_base":
                kb_result = get_kb_context(func_args["query"], k=3)
                tool_result_content = json.dumps({"knowledge_base": kb_result})
            elif func_name == "get_memory":
                tool_result_content = json.dumps(get_memory(email, func_args["memory"]))
            elif func_name == "update_memory":
                update_memory(email, func_args["memory"])
                tool_result_content = f"Memory stored successfully: {func_args['memory']}"
            elif func_name == "get_journal_context":
                tool_result_content = json.dumps(get_journal_context(email, func_args["query"]))
            else:
                logger.warning("Unknown tool called", extra={"email": email, "tool": func_name})
                break

            messages.append({
                "role": "assistant",
                "tool_calls": [{
                    "id": tool_call.id,
                    "type": "function",
                    "function": {"name": func_name, "arguments": json.dumps(func_args)}
                }]
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result_content
            })

        if not reply:
            logger.warning("Agent loop exhausted without reply", extra={"email": email})
            reply = "I'm here with you. Could you share a little more about what you mean?"

        add_session_message(session_id=session_id, email=email, role="user", content=message)
        add_session_message(session_id=session_id, email=email, role="assistant", content=reply)

        # Set the session title from the first user message
        if not history:
            set_session_title(session_id=session_id, email=email, title=message)

        logger.info("Reply generated", extra={"email": email, "session_id": session_id})
        return {"success": True, "reply": reply, "session_id": session_id}

    except Exception as e:
        logger.error("[chat_agent] Error", extra={"email": email, "error": str(e)})
        return {
            "success": False,
            "message": "Something went wrong. Please try again later."
        }
