from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.utils.schema import SendNotificationModel
from app.services.db.notification_utils import send_notification
from app.services.db.mongo_utils import user_profile
from app.services import event_bus
from app.utils.logger_config import logger

notifications_router = APIRouter()


@notifications_router.post("/notifications/send")
def send(data: SendNotificationModel):
    if data.target != "all":
        email = data.target.lower()
        if not user_profile.find_one({"email": email}, {"_id": 1}):
            return JSONResponse(
                {"error": f"User with email '{email}' not found."},
                status_code=404,
            )
        data.target = email

    emails = send_notification(
        target=data.target,
        notif_type=data.type,
        title=data.title,
        body=data.body,
        data=data.data,
    )

    sse_payload = {
        "type": data.type,
        "title": data.title,
        "body": data.body,
        "data": data.data,
    }
    for email in emails:
        event_bus.publish(email, sse_payload)

    logger.info("Notification dispatched", extra={"target": data.target, "total": len(emails)})
    return {"success": True, "delivered_to": len(emails)}
