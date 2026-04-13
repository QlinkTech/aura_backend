import time
from bson import ObjectId
from bson.errors import InvalidId
from app.services.db.mongo_utils import journal_log
from app.utils.logger_config import logger


def save_journal_log(
    email: str,
    journal_prompt: str,
    journal_entry: str,
    title: str,
    summary: str,
    mood: str,
    mood_score: int,
    people: list,
    theme: str
) -> str:
    """Insert a journal log document and return the inserted id."""
    try:
        log_doc = {
            "email": email,
            "journal_prompt": journal_prompt,
            "journal_entry": journal_entry,
            "title": title,
            "summary": summary,
            "mood": mood,
            "mood_score": mood_score,
            "people": people,
            "theme": theme,
            "created_at": int(time.time())
        }
        result = journal_log.insert_one(log_doc)
        log_id = str(result.inserted_id)
        logger.info("Journal log saved", extra={"email": email, "log_id": log_id})
        return log_id
    except Exception as e:
        logger.error("Error saving journal log", extra={"email": email, "error": str(e)})
        raise e


def _serialize(doc: dict) -> dict:
    """Convert ObjectId _id to string log_id."""
    doc["log_id"] = str(doc.pop("_id"))
    return doc


def get_journal_logs(email: str, limit: int = None) -> list:
    """Fetch journal logs for a user, newest first. Pass limit to cap results."""
    try:
        cursor = journal_log.find({"email": email}).sort("created_at", -1)
        if limit:
            cursor = cursor.limit(limit)
        logs = [_serialize(doc) for doc in cursor]
        logger.info("Journal logs fetched", extra={"email": email, "count": len(logs)})
        return logs
    except Exception as e:
        logger.error("Error fetching journal logs", extra={"email": email, "error": str(e)})
        raise e


def get_journal_log_by_id(email: str, log_id: str) -> dict | None:
    """Fetch a single journal log by its id, scoped to the user."""
    try:
        doc = journal_log.find_one({"_id": ObjectId(log_id), "email": email})
        if not doc:
            return None
        return _serialize(doc)
    except InvalidId:
        return None
    except Exception as e:
        logger.error("Error fetching journal log", extra={"email": email, "log_id": log_id, "error": str(e)})
        raise e


def delete_journal_log(email: str, log_id: str) -> bool:
    """Delete a journal log from MongoDB. Returns True if deleted, False if not found."""
    try:
        result = journal_log.delete_one({"_id": ObjectId(log_id), "email": email})
        deleted = result.deleted_count > 0
        logger.info("Journal log deleted from MongoDB", extra={"email": email, "log_id": log_id, "deleted": deleted})
        return deleted
    except InvalidId:
        return False
    except Exception as e:
        logger.error("Error deleting journal log", extra={"email": email, "log_id": log_id, "error": str(e)})
        raise e
