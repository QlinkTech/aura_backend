import time
import uuid
from bson import ObjectId
from app.services.db.mongo_utils import eft_sessions
from app.utils.logger_config import logger


def create_eft_session(email: str) -> str:
    session_id = str(uuid.uuid4())
    doc = {
        "session_id": session_id,
        "email": email,
        "messages": [],
        "is_complete": False,
        "audio_url": None,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }
    eft_sessions.insert_one(doc)
    logger.info("EFT session created", extra={"email": email, "session_id": session_id})
    return session_id


def get_eft_session(session_id: str, email: str) -> dict | None:
    doc = eft_sessions.find_one(
        {"session_id": session_id, "email": email},
        {"_id": 0}
    )
    return doc


def add_session_message(session_id: str, role: str, content: str):
    eft_sessions.update_one(
        {"session_id": session_id},
        {
            "$push": {"messages": {"role": role, "content": content}},
            "$set": {"updated_at": int(time.time())},
        }
    )


def get_session_messages(session_id: str, email: str) -> list:
    doc = eft_sessions.find_one(
        {"session_id": session_id, "email": email},
        {"messages": 1, "_id": 0}
    )
    return doc.get("messages", []) if doc else []


def mark_session_complete(session_id: str, audio_url: str):
    eft_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"is_complete": True, "audio_url": audio_url, "updated_at": int(time.time())}}
    )
    logger.info("EFT session marked complete", extra={"session_id": session_id})


def list_eft_sessions(email: str) -> list:
    cursor = eft_sessions.find(
        {"email": email},
        {"_id": 0, "messages": 0}
    ).sort("created_at", -1)
    return list(cursor)


def delete_eft_session(session_id: str, email: str) -> bool:
    result = eft_sessions.delete_one({"session_id": session_id, "email": email})
    deleted = result.deleted_count > 0
    logger.info("EFT session delete", extra={"session_id": session_id, "deleted": deleted})
    return deleted
