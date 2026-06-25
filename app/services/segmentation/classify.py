import time
from app.services.db.mongo_utils import (
    user_profile, chat_sessions, eft_sessions,
    guided_viz_sessions, journal_log, activity_log,
)
from app.utils.logger_config import logger

ACTIVITY_COLLECTIONS = [chat_sessions, eft_sessions, guided_viz_sessions, journal_log, activity_log]

_CONVERTED_STATUSES = {"active", "authenticated", "charged"}

SECONDS_PER_DAY = 24 * 60 * 60
CURRENT_TIER_WINDOW_SECONDS = 30 * SECONDS_PER_DAY


def compute_active_days(email: str, start_ts: int, end_ts: int) -> int:
    """Count distinct calendar days with activity for this user in [start_ts, end_ts]."""
    days = set()
    for col in ACTIVITY_COLLECTIONS:
        for doc in col.find(
            {"email": email, "created_at": {"$gte": start_ts, "$lte": end_ts}},
            {"created_at": 1},
        ):
            days.add(doc["created_at"] // SECONDS_PER_DAY)
    return len(days)


def classify_engagement_tier(active_days: int) -> str:
    if active_days >= 20:
        return "daily"
    if active_days >= 12:
        return "high"
    if active_days >= 6:
        return "medium"
    if active_days >= 1:
        return "low"
    return "inactive"


def classify_engagement_status(trial_tier: str, current_tier: str, converted: bool) -> str:
    if converted:
        return "converted"
    if current_tier in ("medium", "high", "daily"):
        return "hot"
    if current_tier == "low" or trial_tier in ("medium", "high", "daily"):
        return "warm"
    return "cold"


def _rolling_current_tier(email: str, now: int) -> str:
    current_active_days = compute_active_days(email, now - CURRENT_TIER_WINDOW_SECONDS, now)
    return classify_engagement_tier(current_active_days)


def classify_user(user_doc: dict, now: int = None) -> dict:
    """
    engagement_tier: a rolling "how are they doing right now" tier (trailing 30 days).
    trial_engagement_tier: frozen tier of activity during [trial_start_at, trial_end_at] —
    stops growing once the trial ends, so it always reflects trial-period behavior only.
    engagement_status: cold/warm/hot/converted/no_trial — single funnel-temperature read.
    """
    now = now if now is not None else int(time.time())
    email = user_doc["email"]

    converted = user_doc.get("subscription_status") in _CONVERTED_STATUSES
    if converted:
        # Trial history is irrelevant once they're a paying customer — only track current usage.
        return {
            "engagement_tier": _rolling_current_tier(email, now),
            "trial_engagement_tier": None,
            "engagement_status": "converted",
        }

    trial_end_at = user_doc.get("trial_end_at")
    if not trial_end_at:
        return {"engagement_tier": None, "trial_engagement_tier": None, "engagement_status": "no_trial"}

    trial_start_at = user_doc.get("trial_start_at", trial_end_at - 30 * SECONDS_PER_DAY)
    trial_active_days = compute_active_days(email, trial_start_at, min(now, trial_end_at))
    trial_tier = classify_engagement_tier(trial_active_days)

    current_tier = trial_tier if now < trial_end_at else _rolling_current_tier(email, now)

    return {
        "engagement_tier": current_tier,
        "trial_engagement_tier": trial_tier,
        "engagement_status": classify_engagement_status(trial_tier, current_tier, converted),
    }


def run_classification():
    now = int(time.time())
    classified = 0
    for user_doc in user_profile.find(
        {},
        {"email": 1, "trial_start_at": 1, "trial_end_at": 1, "subscription_status": 1},
    ):
        try:
            result = classify_user(user_doc, now=now)
            user_profile.update_one(
                {"_id": user_doc["_id"]},
                {
                    "$set": {**result, "classified_at": now},
                    "$unset": {"lifecycle_bucket": "", "lifecycle_label": ""},
                },
            )
            classified += 1
        except Exception as e:
            logger.error("Failed to classify user", extra={"email": user_doc.get("email"), "error": str(e)})
    logger.info("Lifecycle classification run complete", extra={"classified": classified})
