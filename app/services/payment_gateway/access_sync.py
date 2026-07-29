import time
from app.services.db.mongo_utils import user_profile
from app.services.mail.client import send_trial_ended_email
from app.services.gupshup.lifecycle import send_trial_ended_whatsapp
from app.utils.logger_config import logger

# Mirrors the access-grant set in app.services.auth_service.get_active_user —
# these are the subscription_status values that mean "currently genuinely paying."
_ACTIVE_SUBSCRIPTION_STATUSES = {"active", "completed", "authenticated"}
# Mirrors the lazy-revoke condition in get_active_user / login / google_login, plus:
# - "expired" — created but never paid before expire_by; only surfaces via direct
#   API reconciliation, never by webhook.
# - "halted" — Razorpay auto-halts a subscription after repeated failed payment
#   retries; the webhook path already revokes is_paid for this, but a missed
#   webhook would otherwise never get corrected without this in the set.
_LAPSED_SUBSCRIPTION_STATUSES = {"cancelled", "paused", "free", "expired", "halted"}


def _is_orphaned_grant(user_doc: dict) -> bool:
    """is_paid=True with nothing at all backing it — no subscription_status, no
    trial, no Razorpay subscription ever created. Not a real trial/payment, just
    a stale or manually-set flag that should have gone through is_bypassed instead."""
    return (
        not user_doc.get("subscription_status")
        and not user_doc.get("trial_end_at")
        and not user_doc.get("early_bird_sub_id")
    )


def _compute_is_paid(user_doc: dict, now: int) -> bool:
    is_paid = user_doc.get("is_paid", False)
    sub_status = user_doc.get("subscription_status")
    trial_end_at = user_doc.get("trial_end_at", 0)
    paid_until = user_doc.get("paid_until", 0)

    if not is_paid:
        # Self-heal: should be paid but isn't (missed webhook, active trial never picked up).
        if trial_end_at and now < trial_end_at:
            return True
        if paid_until and now < paid_until:
            return True
        if sub_status in _ACTIVE_SUBSCRIPTION_STATUSES:
            return True
        return False

    # is_paid is currently True — only revoke on a trusted signal.
    # A cancelled/halted status doesn't end access early if a paid-up period is
    # still running (e.g. cancel-at-cycle-end) — status means "won't renew", not
    # "access ends now".
    if paid_until and now < paid_until:
        return True
    if sub_status in _LAPSED_SUBSCRIPTION_STATUSES and now >= trial_end_at:
        return False
    if _is_orphaned_grant(user_doc):
        return False
    return True


def sync_access_status():
    """
    Daily ground-truth recompute of is_paid, instead of relying on the lazy
    per-request check in auth_service.get_active_user / login / google_login.
    Applies to bypassed users too (for data accuracy) — access itself is unaffected,
    since get_active_user grants access via is_bypassed before ever checking is_paid.
    """
    now = int(time.time())
    updated = 0
    for user_doc in user_profile.find(
        {},
        {"email": 1, "is_paid": 1, "is_bypassed": 1, "subscription_status": 1, "trial_end_at": 1, "early_bird_sub_id": 1, "paid_until": 1},
    ):
        old_is_paid = user_doc.get("is_paid", False)
        new_is_paid = _compute_is_paid(user_doc, now)
        if new_is_paid == old_is_paid:
            continue

        email = user_doc["email"]
        user_profile.update_one({"_id": user_doc["_id"]}, {"$set": {"is_paid": new_is_paid, "updated_at": now}})
        updated += 1

        # Only a genuinely lapsed trial warrants the "trial ended" email — requires an
        # actual trial_end_at, not just a lapsed-looking status. Users like an abandoned
        # Razorpay checkout (subscription_status="expired", no trial_end_at) never had a
        # trial to begin with, so that email would be the wrong message for them.
        is_lapsed_trial = user_doc.get("subscription_status") in _LAPSED_SUBSCRIPTION_STATUSES and bool(user_doc.get("trial_end_at"))
        if old_is_paid and not new_is_paid and is_lapsed_trial and not user_doc.get("is_bypassed"):
            try:
                send_trial_ended_email(to_email=email)
                # remove_contact_from_list(email=email, list_id=LIST_TRIAL)
            except Exception as e:
                logger.error("Failed to send trial ended email during access sync", extra={"email": email, "error": str(e)})
            send_trial_ended_whatsapp(email=email)

    logger.info("Access status sync complete", extra={"updated": updated})
