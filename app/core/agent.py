
from openai import OpenAI
from app.utils.db.mongo_utils import add_chat_history, get_last_chat_history, return_system_prompt
from app.utils.db.pinecone_utils import upsert_data, fetch_data, upsert_kb, fetch_kb
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
        embedding = get_embedding(memory)
        upsert_data(
            user_id=user,
            vector=embedding,
            text=memory
        )
    except Exception as e:
        print(f"[update_memory] Error: {e}")
        raise e


def get_memory(user: str, memory: str):
    try:
        embedding = get_embedding(memory)
        results = fetch_data(
            user_id=user,
            vector=embedding
        )
        value = []
        for match in results:
            if 'text' in match['metadata']:
                value.append(match['metadata']['text'])
        return {"long_term_memory": "\n".join(value)}
    
    except Exception as e:
        print(f"[get_memory] Error: {e}")
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
        return "\n".join(context)
    except Exception as e:
        print(f"[get_kb_context] Error: {e}")
        return ""
        
def update_kb(doc_id: str, text: str):
    """Insert/update therapist knowledge docs into KB vector DB"""
    try:
        embedding = get_embedding(text)
        upsert_kb(
            doc_id=doc_id,
            vector=embedding,
            text=text
        )
    except Exception as e:
        print(f"[update_kb] Error: {e}")
        raise e

def chat_agent(email: str, message: str):
    email = email.lower()

    prompt = return_system_prompt()
    if prompt:
        mmd_system_prompt = prompt.get("prompt", system_prompt)

    try:
        history = get_last_chat_history(email)

        kb_context = get_kb_context(message, k=3)
        rag_context = f"\n---\nTherapist Knowledge Base:\n{kb_context}\n---\n"

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": mmd_system_prompt + rag_context},
                {"role": "system", "content": f"Chat history: {history}"},
                {"role": "user", "content": f"user message: {message}"}
            ],
            tools=tools,
            tool_choice="auto",
            temperature=1.33
        )

        result = response.choices[0]

        if result.finish_reason == "tool_calls":
            tool_call = result.message.tool_calls[0]
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments)

            if func_name == "get_memory":
                memory_result = get_memory(email, func_args["memory"])

                follow_up = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
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
                            "content": json.dumps(memory_result)  # or whatever result you want to pass
                        }
                    ],
                    temperature=0.7
                )

                reply = follow_up.choices[0].message.content

            elif func_name == "update_memory":
                update_memory(email, func_args["memory"])
                follow_up = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
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
                            "content": f"Memory stored successfully: {func_args['memory']}"
                        }
                    ],
                    temperature=0.7
                )
                reply = follow_up.choices[0].message.content

            add_chat_history(email, "user", message)
            add_chat_history(email, "assistant", reply)

            return {
                "success": True,
                "reply": reply
            }

        # No tool call — direct reply
        reply = result.message.content
        add_chat_history(email, "user", message)
        add_chat_history(email, "assistant", reply)

        return {
            "success": True,
            "reply": reply
        }

    except Exception as e:
        print(f"[chat_agent] Error: {e}")
        return {
            "success": False,
            "message": "Something went wrong. Please try again later."
        }
