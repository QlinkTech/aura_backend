import time
from app.services.db.mongo_utils import user_profile
from app.services.payment_gateway.client import fetch_subscription
from app.utils.logger_config import logger


def reconcile_pending_subscriptions():
    """
    Users with an early_bird_sub_id but no subscription_status — a Razorpay
    subscription was created for them but we never got (or missed) the webhook
    confirming its status. Poll Razorpay directly and backfill subscription_status
    from ground truth, so access_sync.sync_access_status() can act on it.
    """
    now = int(time.time())
    reconciled = 0
    query = {
        "early_bird_sub_id": {"$exists": True, "$ne": None},
        "subscription_status": {"$exists": False},
    }
    for user_doc in user_profile.find(query, {"email": 1, "early_bird_sub_id": 1}):
        email = user_doc["email"]
        sub_id = user_doc["early_bird_sub_id"]
        try:
            sub = fetch_subscription(sub_id)
        except Exception as e:
            logger.error("Failed to fetch subscription during reconciliation", extra={"email": email, "sub_id": sub_id, "error": str(e)})
            continue

        status = sub.get("status")
        if not status:
            continue

        user_profile.update_one(
            {"_id": user_doc["_id"]},
            {"$set": {"subscription_status": status, "updated_at": now}},
        )
        reconciled += 1
        logger.info("Reconciled subscription_status from Razorpay", extra={"email": email, "sub_id": sub_id, "status": status})

    logger.info("Subscription reconciliation complete", extra={"reconciled": reconciled})
