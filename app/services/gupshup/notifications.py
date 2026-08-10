"""WhatsApp mirrors of the in-app notifications.

The in-app notifications (see `notification_utils` + `event_bus`) only reach a user with
the web app open, or whenever they next open it. These are the same five moments delivered
to WhatsApp, where the user actually is:

    guided viz ready · EFT session ready · vision board ready   (per-user, they asked for it)
    new masterclass · new resource live                          (broadcast to everyone)

Every send here is best-effort and never raises — a WhatsApp failure must not fail the
generation job or the admin publish request that produced the notification.

All five are UTILITY-category templates: each one reports on something that just happened
inside the user's own account, which is what lets them reach a verified number without a
marketing opt-in. Keep any copy change inside that boundary — the moment a template starts
selling rather than reporting, Meta recategorises it as MARKETING and delivery silently
narrows to opted-in users at a higher price.

The broadcasts deliberately go through the campaign machinery (`whatsapp_campaign_utils`)
rather than looping over users here, so an auto-broadcast gets the same per-recipient
delivery tracking, outage abort and dashboard retry as a hand-built campaign.
"""

import re
from datetime import datetime, timedelta, timezone

from app.services.db.mongo_utils import user_profile
from app.services.db.whatsapp_campaign_utils import create_campaign, run_campaign
from app.services.gupshup.client import send_template_message
from app.utils.env_load import (
    eft_ready_template_id,
    guided_viz_ready_template_id,
    new_masterclass_template_id,
    new_resource_template_id,
    vision_board_ready_template_id,
)
from app.utils.logger_config import logger

_NAME_FALLBACK = "there"

# Masterclass times are stored as a bare epoch and rendered by the frontend in the user's own
# locale — a WhatsApp message has no such luxury, so it states one explicit timezone. Fixed
# offset rather than ZoneInfo("Asia/Kolkata"): India has no DST, and the slim runtime image
# carries no tz database.
_IST = timezone(timedelta(hours=5, minutes=30))

# The noun each resource category gets called in the message body ("a new {{2}} has been added").
_RESOURCE_LABEL = {
    "masterclass_vault": "masterclass recording",
    "downloadables": "resource",
    "audio": "audio session",
}


def _clean_param(value: str) -> str:
    """Collapses whitespace in an admin-entered value — WhatsApp rejects template params
    containing newlines, tabs, or runs of more than four spaces."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _name_of(user: dict) -> str:
    return _clean_param(user.get("username")) or _NAME_FALLBACK


def format_masterclass_time(epoch: int) -> str:
    """Renders a masterclass start time for a message body, e.g. 'Tue, 12 Aug · 7:00 PM IST'."""
    try:
        dt = datetime.fromtimestamp(int(epoch), _IST)
    except (TypeError, ValueError, OSError):
        return ""
    # %-d/%-I (no zero padding) are glibc/BSD extensions — both the macOS dev machine and the
    # Debian-slim image support them.
    return dt.strftime("%a, %-d %b · %-I:%M %p IST")


def _notify_user(email: str, template_id: str, event: str, body_params: list = None, button_params: list = None) -> None:
    """Sends one utility template to a single user's verified WhatsApp number.

    Gupshup takes body and button variables as one flat list, body first — so the params
    sent are [name, *body_params, *button_params]. Splitting them in the signature keeps
    that ordering explicit: `button_params` fills the {{n}} at the end of a deep-link
    button's URL, and getting the two mixed up produces a message that looks right but
    links to the wrong place.

    Skips silently when the user never verified a number or the template id isn't
    configured yet. Never raises."""
    try:
        if not template_id:
            logger.warning("WhatsApp notification skipped — template id not configured", extra={"event": event, "email": email})
            return

        user = user_profile.find_one({"email": email}, {"username": 1, "phone": 1, "phone_verified": 1})
        if not user or not user.get("phone_verified") or not user.get("phone"):
            logger.info("WhatsApp notification skipped — no verified phone", extra={"event": event, "email": email})
            return

        message_id = send_template_message(
            phone_number=user["phone"],
            template_id=template_id,
            params=[_name_of(user), *(body_params or []), *(button_params or [])],
        )
        logger.info("WhatsApp notification sent", extra={"event": event, "email": email, "message_id": message_id})
    except Exception as e:
        logger.error("Failed to send WhatsApp notification", extra={"event": event, "email": email, "error": str(e)})


def _broadcast(template_id: str, event: str, campaign_name: str, body_params: list, button_params: list = None) -> None:
    """Creates and runs a campaign of one utility template to every user with a phone number.

    Blocking (sends serially) — call it from a background task, not inline in a request.
    Never raises. The first param is a per-recipient field reference so each user still gets
    their own name; the rest are the fixed strings the caller passes in, body variables
    before button ones (see `_notify_user` for why the order matters)."""
    try:
        if not template_id:
            logger.warning("WhatsApp broadcast skipped — template id not configured", extra={"event": event})
            return

        campaign = create_campaign(
            name=campaign_name,
            template_id=template_id,
            params=[{"field": "username", "fallback": _NAME_FALLBACK}, *body_params, *(button_params or [])],
            target="all",
        )
        logger.info("WhatsApp broadcast created", extra={"event": event, "campaign_id": campaign["campaign_id"], "recipients": campaign["total_recipients"]})
        run_campaign(campaign["campaign_id"])
    except Exception as e:
        logger.error("Failed to send WhatsApp broadcast", extra={"event": event, "campaign_name": campaign_name, "error": str(e)})


# ==== PER-USER NOTIFICATIONS ====

def send_guided_viz_ready_whatsapp(email: str, session_id: str) -> None:
    """Mirrors the 'guided_viz_complete' in-app notification. The button deep-links straight
    to this session: /visualization?session=<session_id>."""
    _notify_user(email, guided_viz_ready_template_id, "guided_viz_complete", button_params=[session_id])


def send_eft_ready_whatsapp(email: str, session_id: str) -> None:
    """Mirrors the 'eft_complete' in-app notification. The button deep-links straight to this
    session: /eft-tapping?session=<session_id>."""
    _notify_user(email, eft_ready_template_id, "eft_complete", button_params=[session_id])


def send_vision_board_ready_whatsapp(email: str) -> None:
    """Sent alongside the vision-board-ready email once the board finishes generating."""
    _notify_user(email, vision_board_ready_template_id, "vision_board_complete")


# ==== BROADCASTS ====

def broadcast_new_masterclass_whatsapp(title: str, datetime_ts: int) -> None:
    """Mirrors the 'new_masterclass' in-app notification. Runs as a background task."""
    clean_title = _clean_param(title)
    when = format_masterclass_time(datetime_ts) or "Details on your events page"
    _broadcast(
        template_id=new_masterclass_template_id,
        event="new_masterclass",
        campaign_name=f"Auto · New masterclass — {clean_title}",
        body_params=[clean_title, when],
    )


def broadcast_new_resource_whatsapp(name: str, category: str, resource_id: str) -> None:
    """Mirrors the 'new_resource' in-app notification. Runs as a background task. The button
    deep-links to this resource: /resources?resource=<resource_id>."""
    clean_name = _clean_param(name)
    _broadcast(
        template_id=new_resource_template_id,
        event="new_resource",
        campaign_name=f"Auto · New resource — {clean_name}",
        body_params=[_RESOURCE_LABEL.get(category, "resource"), clean_name],
        button_params=[resource_id],
    )
