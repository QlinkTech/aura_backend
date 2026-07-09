from fastapi import APIRouter, Request
from app.services.db.whatsapp_campaign_utils import handle_message_event, handle_meta_statuses
from app.utils.logger_config import logger

whatsapp_webhook_router = APIRouter()


@whatsapp_webhook_router.post("/webhook")
async def gupshup_webhook(request: Request):
    """Receives Gupshup delivery callbacks (sent/delivered/read/failed) in either the native
    Gupshup format ({"type": "message-event", ...}) or the Meta/Cloud-API format
    ({"entry": [{"changes": [{"value": {"statuses": [...]}}]}]}) and updates campaign stats."""
    try:
        event = await request.json()
    except Exception:
        return {"status": "ignored"}

    try:
        if event.get("type") == "message-event":
            handle_message_event(event)
        elif "entry" in event:
            for entry in event.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if "statuses" in value:
                        handle_meta_statuses(value)
                    # inbound user messages ("messages" in value) are ignored — no chatbot here
    except Exception as e:
        logger.error("Failed to process Gupshup webhook event", extra={"error": str(e)})

    # Always ack with 200 so Gupshup doesn't retry/disable the callback
    return {"status": "ok"}
