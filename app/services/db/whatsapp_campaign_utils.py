import re
import time
from bson import ObjectId
from fastapi import HTTPException, status
from app.services.db.mongo_utils import user_profile, whatsapp_campaigns, whatsapp_campaign_messages
from app.services.gupshup.client import send_template_message
from app.utils.logger_config import logger

VALID_TIERS = {"daily", "high", "medium", "low", "inactive"}

# Fields a campaign param is allowed to pull from user_profile for per-recipient personalization.
# Deliberately an allowlist, not "whatever's in params" — this data goes straight into a WhatsApp
# message, so it must exclude anything sensitive (password hashes, tokens, etc.) even if a caller asks for it.
PROFILE_FIELD_LABELS = {
    "username": "Name",
    "email": "Email",
    "phone": "Phone number",
    "engagement_tier": "Engagement tier (current)",
    "trial_engagement_tier": "Engagement tier (during trial)",
    "engagement_status": "Engagement status (cold/warm/hot/converted)",
    "subscription_status": "Subscription status",
}
ALLOWED_PROFILE_FIELDS = set(PROFILE_FIELD_LABELS)


def list_personalization_fields() -> list:
    """Fields the frontend can offer for per-recipient params, e.g. {"field": "username", "fallback": "there"}."""
    return [{"field": field, "label": label} for field, label in PROFILE_FIELD_LABELS.items()]

# Delivery lifecycle: a status only ever moves forward; "failed" is terminal.
_STATUS_RANK = {"pending": 0, "submitted": 1, "sent": 2, "delivered": 3, "read": 4, "failed": 5}


def _normalize_manual_numbers(numbers: list) -> list:
    """Strips formatting from manually entered numbers, validates, and dedupes preserving order."""
    if not numbers:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="numbers must be a non-empty list of phone numbers")

    cleaned, seen, invalid = [], set(), []
    for raw in numbers:
        digits = re.sub(r"\D", "", str(raw))
        if len(digits) < 8 or len(digits) > 15:
            invalid.append(str(raw))
        elif digits not in seen:
            seen.add(digits)
            cleaned.append(digits)

    if invalid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid phone numbers: {', '.join(invalid)}")
    return cleaned


def _normalize_params(params: list) -> list:
    """Converts each param to a plain str (fixed) or dict (field ref), validating field refs against the allowlist."""
    normalized = []
    for p in params:
        if isinstance(p, str):
            normalized.append(p)
            continue
        spec = p.model_dump() if hasattr(p, "model_dump") else dict(p)
        if spec.get("field") not in ALLOWED_PROFILE_FIELDS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"params.field must be one of: {', '.join(sorted(ALLOWED_PROFILE_FIELDS))}",
            )
        normalized.append(spec)
    return normalized


def _resolve_params(params: list, recipient: dict) -> list:
    """Fills each param for one recipient: fixed strings pass through, field refs pull from the recipient's profile data."""
    resolved = []
    for p in params:
        if isinstance(p, str):
            resolved.append(p)
        else:
            value = recipient.get(p["field"])
            resolved.append(str(value) if value not in (None, "") else p.get("fallback", ""))
    return resolved


def resolve_recipients(target: str, tiers: list = None, numbers: list = None, extra_fields: set = None) -> list:
    """Returns [{email, phone, <extra_fields>...}] — users with a phone (optionally tier-filtered), or manually entered numbers."""
    extra_fields = extra_fields or set()
    projection = {"_id": 0, "email": 1, "phone": 1, **{f: 1 for f in extra_fields}}

    if target == "numbers":
        phones = _normalize_manual_numbers(numbers)
        # attach profile data for numbers that belong to known users, so stats + personalization stay traceable;
        # numbers with no matching user fall back to {} (field params use their configured fallback value)
        known = {doc["phone"]: doc for doc in user_profile.find({"phone": {"$in": phones}}, projection)}
        return [{**known.get(p, {}), "email": known.get(p, {}).get("email"), "phone": p} for p in phones]

    query = {"phone": {"$nin": [None, ""]}}
    if target == "tiers":
        invalid = set(tiers or []) - VALID_TIERS
        if not tiers or invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"tiers must be a non-empty subset of: {', '.join(sorted(VALID_TIERS))}",
            )
        query["engagement_tier"] = {"$in": tiers}

    return list(user_profile.find(query, projection))


def create_campaign(name: str, template_id: str, params: list, target: str, tiers: list = None, numbers: list = None,
                    media_type: str = None, media_url: str = None, media_id: str = None) -> dict:
    if media_type and not (media_url or media_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="media_url or media_id is required when media_type is set")
    if (media_url or media_id) and not media_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="media_type is required when media_url/media_id is set")

    normalized_params = _normalize_params(params)
    extra_fields = {p["field"] for p in normalized_params if isinstance(p, dict)}

    recipients = resolve_recipients(target, tiers, numbers, extra_fields)
    if not recipients:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No users with a phone number match this audience")

    now = int(time.time())
    campaign_doc = {
        "name": name,
        "template_id": template_id,
        "params": normalized_params,
        "target": target,
        "tiers": tiers if target == "tiers" else None,
        "numbers": [r["phone"] for r in recipients] if target == "numbers" else None,
        "media_type": media_type,
        "media_url": media_url,
        "media_id": media_id,
        "total_recipients": len(recipients),
        "status": "processing",
        "created_at": now,
        "completed_at": None,
    }
    campaign_id = whatsapp_campaigns.insert_one(campaign_doc).inserted_id

    whatsapp_campaign_messages.insert_many([
        {
            "campaign_id": campaign_id,
            "email": r.get("email"),
            "phone": r["phone"],
            "params": _resolve_params(normalized_params, r),
            "gupshup_message_id": None,
            "status": "pending",
            "error": None,
            "updated_at": now,
        }
        for r in recipients
    ])

    logger.info("WhatsApp campaign created", extra={"campaign_id": str(campaign_id), "campaign_name": name, "recipients": len(recipients)})
    return {"campaign_id": str(campaign_id), "total_recipients": len(recipients)}


def run_campaign(campaign_id: str) -> None:
    """Sends the template to every pending recipient of a campaign. Runs as a background task."""
    oid = ObjectId(campaign_id)
    campaign = whatsapp_campaigns.find_one({"_id": oid})
    if not campaign:
        logger.error("Campaign not found for sending", extra={"campaign_id": campaign_id})
        return

    sent = failed = 0
    for msg in whatsapp_campaign_messages.find({"campaign_id": oid, "status": "pending"}):
        try:
            message_id = send_template_message(
                phone_number=msg["phone"],
                template_id=campaign["template_id"],
                params=msg["params"],
                media_type=campaign.get("media_type"),
                media_url=campaign.get("media_url"),
                media_id=campaign.get("media_id"),
            )
            whatsapp_campaign_messages.update_one(
                {"_id": msg["_id"]},
                {"$set": {"gupshup_message_id": message_id, "status": "submitted", "updated_at": int(time.time())}},
            )
            sent += 1
        except Exception as e:
            whatsapp_campaign_messages.update_one(
                {"_id": msg["_id"]},
                {"$set": {"status": "failed", "error": str(e), "updated_at": int(time.time())}},
            )
            failed += 1
            logger.error("Campaign message send failed", extra={"campaign_id": campaign_id, "email": msg["email"], "error": str(e)})

    whatsapp_campaigns.update_one(
        {"_id": oid},
        {"$set": {"status": "completed", "completed_at": int(time.time())}},
    )
    logger.info("WhatsApp campaign run finished", extra={"campaign_id": campaign_id, "submitted": sent, "failed": failed})


def _stats_for(campaign_oid: ObjectId) -> dict:
    counts = {row["_id"]: row["count"] for row in whatsapp_campaign_messages.aggregate([
        {"$match": {"campaign_id": campaign_oid}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ])}
    # "submitted"/"sent" both mean the message left our side but has no delivery receipt yet
    return {
        "pending": counts.get("pending", 0),
        "sent": counts.get("submitted", 0) + counts.get("sent", 0),
        "delivered": counts.get("delivered", 0),
        "read": counts.get("read", 0),
        "failed": counts.get("failed", 0),
    }


def get_campaign(campaign_id: str) -> dict:
    try:
        oid = ObjectId(campaign_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign id")

    campaign = whatsapp_campaigns.find_one({"_id": oid})
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    campaign["id"] = str(campaign.pop("_id"))
    campaign["stats"] = _stats_for(oid)
    return campaign


# "submitted" (our send accepted by Gupshup) and "sent" (Gupshup's own "sent" webhook event) are the
# same user-facing state — merged in stats, so merge here too for a consistent per-contact status.
_DISPLAY_STATUS = {"submitted": "sent"}
STATUS_FILTERS = {"pending", "sent", "delivered", "read", "failed"}


def get_campaign_contacts(campaign_id: str, status_filter: str = None, page_no: int = 1, page_size: int = 50) -> dict:
    """Per-recipient delivery breakdown for a campaign: who received it, who read it, who failed, etc."""
    try:
        oid = ObjectId(campaign_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign id")

    if not whatsapp_campaigns.find_one({"_id": oid}, {"_id": 1}):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    if status_filter and status_filter not in STATUS_FILTERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"status must be one of: {', '.join(sorted(STATUS_FILTERS))}")

    query = {"campaign_id": oid}
    if status_filter:
        db_statuses = [db_status for db_status, display in _DISPLAY_STATUS.items() if display == status_filter] + [status_filter]
        query["status"] = {"$in": db_statuses}

    page_no = max(page_no, 1)
    page_size = min(max(page_size, 1), 200)
    total = whatsapp_campaign_messages.count_documents(query)

    contacts = []
    cursor = whatsapp_campaign_messages.find(query).sort("_id", 1).skip((page_no - 1) * page_size).limit(page_size)
    for doc in cursor:
        contacts.append({
            "email": doc.get("email"),
            "phone": doc.get("phone"),
            "params": doc.get("params", []),
            "status": _DISPLAY_STATUS.get(doc["status"], doc["status"]),
            "error": doc.get("error"),
            "updated_at": doc.get("updated_at"),
        })

    return {"total": total, "page_no": page_no, "page_size": page_size, "contacts": contacts}


def list_campaigns() -> list:
    campaigns = []
    for doc in whatsapp_campaigns.find().sort("created_at", -1):
        oid = doc.pop("_id")
        doc["id"] = str(oid)
        doc["stats"] = _stats_for(oid)
        campaigns.append(doc)
    return campaigns


def _apply_status_update(event_type: str, ids: list, reason: str = None) -> None:
    """Advances a campaign message to event_type if it matches one of ids and the status only moves forward."""
    if event_type not in _STATUS_RANK:
        return

    ids = [i for i in ids if i]
    if not ids:
        return

    msg = whatsapp_campaign_messages.find_one({"gupshup_message_id": {"$in": ids}})
    if not msg:
        return  # not a campaign message (e.g. an OTP) — ignore

    if _STATUS_RANK[event_type] <= _STATUS_RANK.get(msg["status"], 0):
        return  # stale/out-of-order event

    update = {"status": event_type, "updated_at": int(time.time())}
    if event_type == "failed":
        update["error"] = str(reason or "unknown")

    whatsapp_campaign_messages.update_one({"_id": msg["_id"]}, {"$set": update})
    logger.info("Campaign message event applied", extra={"gupshup_message_id": ids[0], "event": event_type})


def handle_message_event(event: dict) -> None:
    """Applies a Gupshup-format message-event webhook (sent/delivered/read/failed) to the matching campaign message."""
    payload = event.get("payload", {})
    _apply_status_update(
        event_type=payload.get("type"),
        ids=[payload.get("gsId"), payload.get("id")],
        reason=payload.get("payload", {}).get("reason"),
    )


def handle_meta_statuses(value: dict) -> None:
    """Applies Meta/Cloud-API-format status callbacks (entry[].changes[].value.statuses[]) forwarded by Gupshup."""
    for status_obj in value.get("statuses", []):
        errors = status_obj.get("errors") or []
        reason = errors[0].get("title") or errors[0].get("message") if errors else None
        _apply_status_update(
            event_type=status_obj.get("type") or status_obj.get("status"),
            ids=[status_obj.get("gs_id"), status_obj.get("id")],
            reason=reason,
        )
