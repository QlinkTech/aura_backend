from fastapi import APIRouter, Depends, HTTPException
from app.services.auth_service import get_current_user
from app.services.db.notification_utils import (
    get_notifications,
    get_unread_count,
    mark_read,
    mark_all_read,
)
from app.utils.logger_config import logger

notifications_user_router = APIRouter()


@notifications_user_router.get("/notifications")
def list_notifications(current_user: dict = Depends(get_current_user)):
    email = current_user["email"]
    items = get_notifications(email)
    unread = sum(1 for n in items if not n["is_read"])
    return {"notifications": items, "unread_count": unread}


@notifications_user_router.get("/notifications/unread-count")
def unread_count(current_user: dict = Depends(get_current_user)):
    email = current_user["email"]
    return {"unread_count": get_unread_count(email)}


@notifications_user_router.post("/notifications/{notification_id}/read")
def read_one(notification_id: str, current_user: dict = Depends(get_current_user)):
    email = current_user["email"]
    updated = mark_read(notification_id=notification_id, email=email)
    if not updated:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}


@notifications_user_router.post("/notifications/read-all")
def read_all(current_user: dict = Depends(get_current_user)):
    email = current_user["email"]
    count = mark_all_read(email)
    logger.info("Marked all notifications read", extra={"email": email, "count": count})
    return {"success": True, "marked_read": count}
