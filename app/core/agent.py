
from openai import OpenAI
from app.services.db.user_profile_utils import add_chat_history, get_last_chat_history
from app.services.db.mongo_utils import return_system_prompt
from app.services.db.pinecone_utils import upsert_data, fetch_data, upsert_kb, fetch_kb, fetch_journal
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

def chat_agent(email: str, message: str):
    email = email.lower()
    logger.info("Chat agent invoked", extra={"email": email, "user_message": message})

    prompt = return_system_prompt()
    if prompt:
        mmd_system_prompt = prompt.get("prompt", system_prompt)

    try:
        history = get_last_chat_history(email)

        kb_context = get_kb_context(message, k=3)
        rag_context = f"\n---\nTherapist Knowledge Base:\n{kb_context}\n---\n"

        response = openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": mmd_system_prompt + rag_context},
                {"role": "system", "content": f"Chat history: {history}"},
                {"role": "user", "content": f"user message: {message}"}
            ],
            tools=tools,
            tool_choice="auto",
            temperature=1.0
        )

        result = response.choices[0]

        if result.finish_reason == "tool_calls":
            tool_call = result.message.tool_calls[0]
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments)

            logger.info("Tool call triggered", extra={"email": email, "tool": func_name, "tool_args": func_args})

            tool_dispatch = {
                "get_memory":         lambda: json.dumps(get_memory(email, func_args["memory"])),
                "update_memory":      lambda: (update_memory(email, func_args["memory"]), f"Memory stored successfully: {func_args['memory']}")[1],
                "get_journal_context": lambda: json.dumps(get_journal_context(email, func_args["query"])),
            }

            tool_result_content = tool_dispatch[func_name]()

            follow_up = openai_client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    *history,
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": func_name,
                                    "arguments": json.dumps(func_args)
                                }
                            }
                        ]
                    },
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result_content
                    }
                ],
                temperature=0.7
            )
            reply = follow_up.choices[0].message.content

            logger.info("Reply generated via tool call", extra={"email": email, "tool": func_name})
            add_chat_history(email, "user", message)
            add_chat_history(email, "assistant", reply)

            return {
                "success": True,
                "reply": reply
            }

        # No tool call — direct reply
        reply = result.message.content
        logger.info("Direct reply generated", extra={"email": email})
        add_chat_history(email, "user", message)
        add_chat_history(email, "assistant", reply)

        return {
            "success": True,
            "reply": reply
        }

    except Exception as e:
        logger.error("[chat_agent] Error", extra={"email": email, "error": str(e)})
        return {
            "success": False,
            "message": "Something went wrong. Please try again later."
        }
