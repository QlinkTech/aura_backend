import re
import time
from typing import Optional
from fastapi import HTTPException, status
from app.services.db.mongo_utils import whatsapp_messages, whatsapp_conversations, user_profile
from app.services.gupshup.client import send_session_message, list_templates
from app.utils.logger_config import logger

# Meta's customer-service window: we may only free-form reply within this long of the user's
# most recent inbound message; outside it, only an approved template can reach them.
WINDOW_SECONDS = 24 * 60 * 60

# Same forward-only status lifecycle as campaign messages (see whatsapp_campaign_utils.py) —
# kept as a separate copy since inbox and campaign messages are unrelated collections.
_STATUS_RANK = {"pending": 0, "submitted": 1, "sent": 2, "delivered": 3, "read": 4, "failed": 5}

_TEXT_TYPE_FIELDS = {
    "image": "image", "video": "video", "document": "document", "audio": "audio", "sticker": "sticker",
}


def _normalize_phone(raw: str) -> str:
    return re.sub(r"\D", "", str(raw or ""))


def _preview(msg_type: str, text: Optional[str]) -> str:
    if msg_type == "text" and text:
        return text[:200]
    return f"[{msg_type}]"


def store_inbound_message(
    phone: str, name: Optional[str], gupshup_message_id: Optional[str], msg_type: str,
    text: Optional[str] = None, media_url: Optional[str] = None, media_id: Optional[str] = None,
    caption: Optional[str] = None, timestamp: Optional[int] = None,
) -> None:
    """Idempotently records one inbound message and refreshes the conversation summary.
    Safe to call repeatedly with the same gupshup_message_id (webhook retries)."""
    phone = _normalize_phone(phone)
    if not phone:
        logger.warning("Inbound WhatsApp message with no usable phone number — dropped", extra={"gupshup_message_id": gupshup_message_id})
        return

    now = int(timestamp or time.time())
    doc = {
        "phone": phone, "direction": "inbound", "message_type": msg_type,
        "text": text, "media_url": media_url, "media_id": media_id, "caption": caption,
        "sender_name": name, "gupshup_message_id": gupshup_message_id,
        "status": "received", "error": None, "admin_username": None, "created_at": now,
    }

    if gupshup_message_id:
        result = whatsapp_messages.update_one(
            {"gupshup_message_id": gupshup_message_id}, {"$setOnInsert": doc}, upsert=True,
        )
        is_new = result.upserted_id is not None
    else:
        whatsapp_messages.insert_one(doc)
        is_new = True

    if not is_new:
        return  # already recorded this message — don't double-count unread/preview

    whatsapp_conversations.update_one(
        {"_id": phone},
        {
            "$set": {
                "phone": phone,
                "contact_name": name or None,
                "last_message_at": now,
                "last_message_preview": _preview(msg_type, text),
                "last_direction": "inbound",
                "last_inbound_at": now,
                "updated_at": now,
            },
            "$inc": {"unread_count": 1},
        },
        upsert=True,
    )
    logger.info("Inbound WhatsApp message stored", extra={"phone": phone, "message_type": msg_type, "gupshup_message_id": gupshup_message_id})


def handle_inbound_native(event: dict) -> None:
    """Parses a Gupshup native `type == "message"` webhook event."""
    payload = event.get("payload", {}) or {}
    inner = payload.get("payload", {}) or {}
    sender = payload.get("sender", {}) or {}
    msg_type = payload.get("type") or "unsupported"

    store_inbound_message(
        phone=sender.get("phone") or payload.get("source"),
        name=sender.get("name"),
        gupshup_message_id=payload.get("id"),
        msg_type=msg_type,
        text=inner.get("text") if msg_type == "text" else None,
        media_url=inner.get("url") if msg_type in _TEXT_TYPE_FIELDS else None,
        media_id=None,
        caption=inner.get("caption"),
        timestamp=int(event["timestamp"] / 1000) if event.get("timestamp") else None,
    )


def handle_inbound_meta(value: dict) -> None:
    """Parses a Meta/Cloud-API-format `value.messages[]` webhook payload forwarded by Gupshup."""
    names_by_wa_id = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts", [])}

    for msg in value.get("messages", []):
        msg_type = msg.get("type") or "unsupported"
        media_obj = msg.get(msg_type, {}) if msg_type in _TEXT_TYPE_FIELDS else {}
        store_inbound_message(
            phone=msg.get("from"),
            name=names_by_wa_id.get(msg.get("from")),
            gupshup_message_id=msg.get("id"),
            msg_type=msg_type,
            text=(msg.get("text") or {}).get("body") if msg_type == "text" else None,
            media_url=media_obj.get("link") or media_obj.get("url"),
            media_id=media_obj.get("id"),
            caption=media_obj.get("caption"),
            timestamp=int(msg["timestamp"]) if msg.get("timestamp") else None,
        )


def apply_inbox_status_event(ids: list, event_type: str, reason: str = None) -> None:
    """Advances an outbound inbox message's status if its gupshup_message_id matches one of `ids`.
    No-op if it belongs to a campaign instead (or isn't found at all) — safe to call unconditionally."""
    if event_type not in _STATUS_RANK:
        return
    ids = [i for i in ids if i]
    if not ids:
        return

    msg = whatsapp_messages.find_one({"gupshup_message_id": {"$in": ids}, "direction": "outbound"})
    if not msg:
        return
    if _STATUS_RANK[event_type] <= _STATUS_RANK.get(msg["status"], 0):
        return  # stale/out-of-order event

    update = {"status": event_type}
    if event_type == "failed":
        update["error"] = str(reason or "unknown")
    whatsapp_messages.update_one({"_id": msg["_id"]}, {"$set": update})
    logger.info("Inbox message status updated", extra={"gupshup_message_id": ids[0], "event": event_type})


def _window_info(last_inbound_at: Optional[int]) -> dict:
    if not last_inbound_at:
        return {"window_open": False, "window_expires_at": None}
    expires_at = last_inbound_at + WINDOW_SECONDS
    return {"window_open": expires_at > time.time(), "window_expires_at": expires_at}


def list_conversations(search: Optional[str] = None, page_no: int = 1, page_size: int = 50) -> dict:
    """Conversations sorted by most recent activity, each augmented with 24h-window status and the
    matching user_profile email (if the number belongs to a known account)."""
    query = {}
    if search:
        query["$or"] = [{"phone": {"$regex": re.escape(search)}}, {"contact_name": {"$regex": re.escape(search), "$options": "i"}}]

    page_no = max(page_no, 1)
    page_size = min(max(page_size, 1), 200)
    total = whatsapp_conversations.count_documents(query)

    cursor = whatsapp_conversations.find(query).sort("last_message_at", -1).skip((page_no - 1) * page_size).limit(page_size)
    conversations = list(cursor)
    emails_by_phone = {
        u["phone"]: u.get("email") for u in user_profile.find(
            {"phone": {"$in": [c["phone"] for c in conversations]}}, {"_id": 0, "phone": 1, "email": 1},
        )
    }

    results = []
    for c in conversations:
        results.append({
            "phone": c["phone"],
            "contact_name": c.get("contact_name"),
            "email": emails_by_phone.get(c["phone"]),
            "last_message_at": c.get("last_message_at"),
            "last_message_preview": c.get("last_message_preview"),
            "last_direction": c.get("last_direction"),
            "unread_count": c.get("unread_count", 0),
            **_window_info(c.get("last_inbound_at")),
        })

    return {"total": total, "page_no": page_no, "page_size": page_size, "conversations": results}


def get_conversation_messages(phone: str, page_no: int = 1, page_size: int = 50) -> dict:
    phone = _normalize_phone(phone)
    page_no = max(page_no, 1)
    page_size = min(max(page_size, 1), 200)

    query = {"phone": phone}
    total = whatsapp_messages.count_documents(query)
    cursor = whatsapp_messages.find(query).sort("created_at", -1).skip((page_no - 1) * page_size).limit(page_size)

    messages = []
    for doc in cursor:
        messages.append({
            "id": str(doc["_id"]), "gupshup_message_id": doc.get("gupshup_message_id"),
            "direction": doc["direction"], "message_type": doc["message_type"], "text": doc.get("text"),
            "media_url": doc.get("media_url"), "media_id": doc.get("media_id"), "caption": doc.get("caption"),
            "sender_name": doc.get("sender_name"), "status": doc.get("status"), "error": doc.get("error"),
            "admin_username": doc.get("admin_username"), "created_at": doc.get("created_at"),
        })
    messages.reverse()  # chronological, oldest first, even though we paged newest-first

    return {"total": total, "page_no": page_no, "page_size": page_size, "messages": messages}


def mark_conversation_read(phone: str) -> dict:
    phone = _normalize_phone(phone)
    result = whatsapp_conversations.update_one({"_id": phone}, {"$set": {"unread_count": 0}})
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return {"phone": phone, "unread_count": 0}


def _approved_templates() -> list:
    try:
        result = list_templates({"status": "APPROVED"})
        return [
            {"id": t.get("id"), "element_name": t.get("elementName"), "category": t.get("category")}
            for t in result.get("templates", [])
        ]
    except Exception as e:
        logger.error("Failed to fetch approved templates for closed-window reply error", extra={"error": str(e)})
        return []


def send_reply(phone: str, text: str, admin_username: Optional[str]) -> dict:
    """Sends a free-form text reply to a conversation with an open 24h window. Raises 400 (with the
    current approved-template list attached) if the window is closed or the number has never messaged us."""
    phone = _normalize_phone(phone)
    conversation = whatsapp_conversations.find_one({"_id": phone})
    window = _window_info(conversation.get("last_inbound_at") if conversation else None)

    if not window["window_open"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "The 24-hour reply window for this number is closed. Send an approved template to reopen it.",
                "window_open": False,
                "templates": _approved_templates(),
            },
        )

    message_id = send_session_message(phone_number=phone, text=text)

    now = int(time.time())
    whatsapp_messages.insert_one({
        "phone": phone, "direction": "outbound", "message_type": "text", "text": text,
        "media_url": None, "media_id": None, "caption": None, "sender_name": None,
        "gupshup_message_id": message_id, "status": "submitted", "error": None,
        "admin_username": admin_username, "created_at": now,
    })
    whatsapp_conversations.update_one(
        {"_id": phone},
        {"$set": {"last_message_at": now, "last_message_preview": _preview("text", text), "last_direction": "outbound", "updated_at": now}},
    )
    logger.info("Inbox reply sent", extra={"phone": phone, "admin_username": admin_username, "gupshup_message_id": message_id})
    return {"phone": phone, "gupshup_message_id": message_id, "status": "submitted", "created_at": now}
