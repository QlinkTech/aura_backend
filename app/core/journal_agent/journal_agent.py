import json
from openai import OpenAI
from app.utils.env_load import openai_api_key
from app.utils.logger_config import logger
from app.services.db.journal_utils import save_journal_log, get_journal_logs
from app.services.db.chat_session_utils import list_chat_sessions, get_session_messages
from app.services.db.pinecone_utils import upsert_journal
from app.core.agent import get_embedding
from app.core.journal_agent.journal_agent_utils import JOURNAL_SYSTEM_PROMPT, JOURNAL_PROMPTS_SYSTEM_PROMPT

openai_client = OpenAI(api_key=openai_api_key)


def journal_agent(email: str, journal_prompt: str, journal_entry: str) -> dict:
    email = email.lower()
    logger.info("Journal agent invoked", extra={"email": email})

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": JOURNAL_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Journal Prompt: {journal_prompt}\n\nJournal Entry: {journal_entry}"
                }
            ],
            temperature=0.4
        )

        raw = response.choices[0].message.content.strip()
        extracted = json.loads(raw)

        title = extracted.get("title", "")
        summary = extracted.get("summary", "")
        mood = extracted.get("mood", "")
        mood_score = extracted.get("mood_score", 5)
        people = extracted.get("people", [])
        theme = extracted.get("theme", "")

        logger.info("Journal extraction complete", extra={"email": email, "mood": mood, "mood_score": mood_score})

        log_id = save_journal_log(
            email=email,
            journal_prompt=journal_prompt,
            journal_entry=journal_entry,
            title=title,
            summary=summary,
            mood=mood,
            mood_score=mood_score,
            people=people,
            theme=theme
        )

        embedding = get_embedding(summary)
        upsert_journal(email=email, vector=embedding, summary=summary, log_id=log_id)

        logger.info("Journal vector stored in Pinecone", extra={"email": email, "log_id": log_id})

        return {
            "success": True,
            "log_id": log_id,
            "title": title,
            "summary": summary,
            "mood": mood,
            "mood_score": mood_score,
            "people": people,
            "theme": theme
        }

    except json.JSONDecodeError as e:
        logger.error("[journal_agent] JSON parse error", extra={"email": email, "error": str(e)})
        return {"success": False, "message": "Failed to parse journal analysis."}
    except Exception as e:
        logger.error("[journal_agent] Error", extra={"email": email, "error": str(e)})
        return {"success": False, "message": "Something went wrong. Please try again later."}


def generate_journal_prompts(email: str) -> dict:
    email = email.lower()
    logger.info("Generating journal prompts", extra={"email": email})

    try:
        recent_logs = get_journal_logs(email, limit=3)

        if not recent_logs:
            return {
                "success": True,
                "prompts": [
                    "What is something you've been carrying lately that you haven't had the chance to put into words?",
                    "Describe a moment this week where you felt most like yourself.",
                    "What emotion keeps showing up for you, and what do you think it's trying to tell you?",
                    "What would you say to yourself a year from now, looking back at where you are today?"
                ]
            }

        context_parts = []
        for i, log in enumerate(recent_logs, 1):
            context_parts.append(
                f"Entry {i}:\n"
                f"  Summary: {log.get('summary', '')}\n"
                f"  Mood: {log.get('mood', '')} (score: {log.get('mood_score', '')})\n"
                f"  Theme: {log.get('theme', '')}\n"
                f"  People mentioned: {', '.join(log.get('people', []))}"
            )
        journal_context = "\n\n".join(context_parts)

        chat_context = ""
        sessions = list_chat_sessions(email)
        if sessions:
            latest_session_id = sessions[0]["session_id"]
            recent_chats = get_session_messages(session_id=latest_session_id, email=email, limit=6)
            if recent_chats:
                chat_lines = [f"  {msg['role'].capitalize()}: {msg['content']}" for msg in recent_chats]
                chat_context = "\n\nRecent conversation with Aura:\n" + "\n".join(chat_lines)

        user_content = f"Recent journal entries:\n\n{journal_context}{chat_context}"

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": JOURNAL_PROMPTS_SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            temperature=0.8
        )

        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)
        prompts = result.get("prompts", [])

        logger.info("Journal prompts generated", extra={"email": email, "count": len(prompts)})
        return {"success": True, "prompts": prompts}

    except json.JSONDecodeError as e:
        logger.error("[generate_journal_prompts] JSON parse error", extra={"email": email, "error": str(e)})
        return {"success": False, "message": "Failed to generate prompts."}
    except Exception as e:
        logger.error("[generate_journal_prompts] Error", extra={"email": email, "error": str(e)})
        return {"success": False, "message": "Something went wrong. Please try again later."}
