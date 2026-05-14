import time
import uuid

from app.services.db.mongo_utils import notifications, user_profile
from app.utils.logger_config import logger


def _build_doc(email: str, notif_type: str, title: str, body: str, data: dict) -> dict:
    return {
        "notification_id": str(uuid.uuid4()),
        "email": email,
        "type": notif_type,
        "title": title,
        "body": body,
        "data": data or {},
        "is_read": False,
        "created_at": int(time.time()),
    }


def send_notification(
    target: str,
    notif_type: str,
    title: str,
    body: str,
    data: dict = None,
) -> list[str]:
    """
    Create notification docs for target users and return their emails.
    target = "all" broadcasts to every user; otherwise treated as a single email.
    """
    if target == "all":
        emails = [
            u["email"]
            for u in user_profile.find({}, {"email": 1, "_id": 0})
            if u.get("email")
        ]
    else:
        emails = [target.lower()]

    if not emails:
        return []

    docs = [_build_doc(e, notif_type, title, body, data) for e in emails]
    notifications.insert_many(docs)
    logger.info(
        "Notifications created",
        extra={"type": notif_type, "target": target, "count": len(docs)},
    )
    return emails


def get_notifications(email: str) -> list[dict]:
    cursor = notifications.find(
        {"email": email},
        {"_id": 0},
    ).sort("created_at", -1)
    return list(cursor)


def get_unread_count(email: str) -> int:
    return notifications.count_documents({"email": email, "is_read": False})


def mark_read(notification_id: str, email: str) -> bool:
    result = notifications.update_one(
        {"notification_id": notification_id, "email": email},
        {"$set": {"is_read": True}},
    )
    return result.modified_count > 0


def mark_all_read(email: str) -> int:
    result = notifications.update_many(
        {"email": email, "is_read": False},
        {"$set": {"is_read": True}},
    )
    return result.modified_count
