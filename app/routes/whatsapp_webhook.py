from fastapi import APIRouter, Request
from app.services.db.whatsapp_campaign_utils import handle_message_event, handle_meta_statuses
from app.services.db.whatsapp_inbox_utils import handle_inbound_native, handle_inbound_meta, apply_inbox_status_event
from app.utils.logger_config import logger

whatsapp_webhook_router = APIRouter()


def _apply_meta_inbox_statuses(value: dict) -> None:
    """Same status events handle_meta_statuses applies to campaign messages, also matched against inbox messages."""
    for status_obj in value.get("statuses", []):
        errors = status_obj.get("errors") or []
        reason = errors[0].get("title") or errors[0].get("message") if errors else None
        apply_inbox_status_event(
            event_type=status_obj.get("type") or status_obj.get("status"),
            ids=[status_obj.get("gs_id"), status_obj.get("id")],
            reason=reason,
        )


@whatsapp_webhook_router.post("/webhook")
async def gupshup_webhook(request: Request):
    """Receives Gupshup callbacks in either the native Gupshup format ({"type": "message-event"/"message", ...})
    or the Meta/Cloud-API format ({"entry": [{"changes": [{"value": {...}}]}]}): delivery statuses
    (sent/delivered/read/failed) update campaign and inbox message stats, and inbound user messages
    are stored for the admin WhatsApp inbox."""
    try:
        event = await request.json()
    except Exception:
        return {"status": "ignored"}

    try:
        if event.get("type") == "message-event":
            handle_message_event(event)
            payload = event.get("payload", {})
            apply_inbox_status_event(
                event_type=payload.get("type"),
                ids=[payload.get("gsId"), payload.get("id")],
                reason=payload.get("payload", {}).get("reason"),
            )
        elif event.get("type") == "message":
            handle_inbound_native(event)
        elif "entry" in event:
            for entry in event.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if "statuses" in value:
                        handle_meta_statuses(value)
                        _apply_meta_inbox_statuses(value)
                    if "messages" in value:
                        handle_inbound_meta(value)
    except Exception as e:
        logger.error("Failed to process Gupshup webhook event", extra={"error": str(e)})

    # Always ack with 200 so Gupshup doesn't retry/disable the callback
    return {"status": "ok"}
