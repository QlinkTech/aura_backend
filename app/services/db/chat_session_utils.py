import time
import uuid
from fastapi import HTTPException, status
from app.services.db.mongo_utils import chat_sessions
from app.utils.logger_config import logger


def create_chat_session(email: str, source: str = "direct") -> str:
    session_id = str(uuid.uuid4())
    chat_sessions.insert_one({
        "session_id": session_id,
        "email": email,
        "title": "New Chat",
        "source": source,
        "messages": [],
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    })
    logger.info("Chat session created", extra={"email": email, "session_id": session_id})
    return session_id


def get_chat_session(session_id: str, email: str) -> dict | None:
    return chat_sessions.find_one(
        {"session_id": session_id, "email": email},
        {"_id": 0}
    )


def list_chat_sessions(email: str, source: str = None) -> list:
    query = {"email": email}
    if source:
        query["source"] = source
    sessions = chat_sessions.find(
        query,
        {"_id": 0, "session_id": 1, "title": 1, "source": 1, "created_at": 1, "updated_at": 1}
    ).sort("updated_at", -1)
    return list(sessions)


def get_session_messages(session_id: str, email: str, limit: int = 20) -> list:
    session = chat_sessions.find_one(
        {"session_id": session_id, "email": email},
        {"messages": 1}
    )
    if not session:
        return []
    messages = session.get("messages", [])
    return messages[-limit:]


def add_session_message(session_id: str, email: str, role: str, content: str, kb_references: list = None, cta: dict = None):
    message = {"role": role, "content": content, "timestamp": int(time.time())}
    if kb_references:
        message["kb_references"] = kb_references
    if cta:
        message["cta"] = cta
    chat_sessions.update_one(
        {"session_id": session_id, "email": email},
        {"$push": {"messages": message}, "$set": {"updated_at": int(time.time())}}
    )


def set_session_title(session_id: str, email: str, title: str):
    # Trim to 60 chars for a clean sidebar display
    trimmed = title[:60].strip()
    chat_sessions.update_one(
        {"session_id": session_id, "email": email},
        {"$set": {"title": trimmed, "updated_at": int(time.time())}}
    )


def delete_chat_session(session_id: str, email: str) -> bool:
    result = chat_sessions.delete_one({"session_id": session_id, "email": email})
    logger.info("Chat session deleted", extra={"email": email, "session_id": session_id})
    return result.deleted_count > 0
