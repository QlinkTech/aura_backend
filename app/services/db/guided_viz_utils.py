import time
from app.services.db.mongo_utils import guided_viz_sessions
from app.utils.logger_config import logger


def create_guided_viz_session(email: str, session_id: str, user_message: str):
    doc = {
        "session_id": session_id,
        "email": email,
        "user_message": user_message,
        "is_complete": False,
        "audio_url": None,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }
    guided_viz_sessions.insert_one(doc)
    logger.info("Guided viz session created", extra={"email": email, "session_id": session_id})


def get_guided_viz_session(session_id: str, email: str) -> dict | None:
    return guided_viz_sessions.find_one(
        {"session_id": session_id, "email": email},
        {"_id": 0}
    )


def mark_session_complete(
    session_id: str,
    audio_url: str,
    theme: str = "",
    mood: str = "",
    tags: list = None,
    script: str = "",
    generation_cost: dict = None,
):
    guided_viz_sessions.update_one(
        {"session_id": session_id},
        {"$set": {
            "is_complete": True,
            "audio_url": audio_url,
            "theme": theme,
            "mood": mood,
            "tags": tags or [],
            "script": script,
            "generation_cost": generation_cost or {},
            "updated_at": int(time.time()),
        }}
    )
    logger.info("Guided viz session marked complete", extra={"session_id": session_id})


def list_guided_viz_sessions(email: str) -> list:
    cursor = guided_viz_sessions.find(
        {"email": email},
        {"_id": 0}
    ).sort("created_at", -1)
    return list(cursor)


def mark_session_error(session_id: str, error_message: str = "") -> None:
    guided_viz_sessions.update_one(
        {"session_id": session_id},
        {"$set": {
            "is_complete": False,
            "error": True,
            "error_message": error_message,
            "updated_at": int(time.time()),
        }}
    )
    logger.info("Guided viz session marked as error", extra={"session_id": session_id})


def delete_guided_viz_session(session_id: str, email: str) -> bool:
    result = guided_viz_sessions.delete_one({"session_id": session_id, "email": email})
    deleted = result.deleted_count > 0
    logger.info("Guided viz session deleted", extra={"session_id": session_id, "deleted": deleted})
    return deleted
