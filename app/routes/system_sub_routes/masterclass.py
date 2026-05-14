import time
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from app.services.db.mongo_utils import masterclass as masterclass_col
from app.services.db.notification_utils import send_notification
from app.services import event_bus
from app.utils.logger_config import logger

masterclass_router = APIRouter()

_FILTER = {"_type": "masterclass"}


def _get() -> dict | None:
    doc = masterclass_col.find_one(_FILTER, {"_id": 0, "_type": 0})
    return doc or None


@masterclass_router.get("/masterclass")
def get_masterclass():
    """Return the current masterclass, or null if none is set."""
    try:
        return {"masterclass": _get()}
    except Exception as e:
        logger.error("System: error fetching masterclass", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@masterclass_router.put("/masterclass")
def upsert_masterclass(data: dict = Body(...)):
    """Create or replace the masterclass. Always only one exists."""
    try:
        title = data.get("title", "").strip()
        meeting_link = data.get("meeting_link", "").strip()
        meeting_id = data.get("meeting_id", "").strip()
        meeting_password = data.get("meeting_password", "").strip()
        datetime_ts = data.get("datetime")

        if not title or not datetime_ts:
            return JSONResponse({"error": "title and datetime are required"}, status_code=400)

        doc = {
            "_type": "masterclass",
            "title": title,
            "datetime": int(datetime_ts),
            "meeting_link": meeting_link,
            "meeting_id": meeting_id,
            "meeting_password": meeting_password,
            "updated_at": int(time.time()),
        }

        masterclass_col.update_one(_FILTER, {"$set": doc}, upsert=True)
        logger.info("System: masterclass upserted", extra={"title": title})

        sse_payload = {
            "type": "new_masterclass",
            "title": "New Masterclass Available",
            "body": title,
            "data": {},
        }
        emails = send_notification(target="all", notif_type="new_masterclass", title="New Masterclass Available", body=title, data={})
        for email in emails:
            event_bus.publish(email, sse_payload)

        return {"success": True, "masterclass": {k: v for k, v in doc.items() if not k.startswith("_")}}

    except Exception as e:
        logger.error("System: error upserting masterclass", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@masterclass_router.delete("/masterclass")
def delete_masterclass():
    """Remove the masterclass (sets it to null for all users)."""
    try:
        result = masterclass_col.delete_one(_FILTER)
        if result.deleted_count == 0:
            return JSONResponse({"error": "No masterclass to delete"}, status_code=404)
        logger.info("System: masterclass deleted")
        return {"success": True}
    except Exception as e:
        logger.error("System: error deleting masterclass", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)
