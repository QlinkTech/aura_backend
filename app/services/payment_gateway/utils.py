import time
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from fastapi import HTTPException, status
from app.utils.db.mongo_utils import user_profile
from app.services.payment_gateway.client import create_subscription, cancel_subscription, fetch_subscription
from app.utils.logger_config import logger

EARLY_BIRD_TRIAL_MONTHS = 3


def _trial_start_at() -> int:
    """Returns Unix timestamp 3 months from now (start of billing after trial)."""
    future = datetime.now(timezone.utc) + relativedelta(months=EARLY_BIRD_TRIAL_MONTHS)
    return int(future.timestamp())

# Subscription is active/paid — do not allow new subscription
_PAID_STATUSES = {"active", "pending", "halted", "completed"}
# Subscription was created but user hasn't paid yet — allow plan switch
_UNPAID_STATUSES = {"created", "authenticated"}

def _create_and_store_subscription(email: str, plan_key: str, expire_by: int = None) -> dict:
    logger.info("Creating subscription", extra={"email": email, "plan_key": plan_key})
    subscription = create_subscription(
        plan_key=plan_key,
        notify_email=email,
        expire_by=expire_by,
        start_at=_trial_start_at(),
    )
    sub_id = subscription.get("id")
    payment_link = subscription.get("short_url", "")
    user_profile.update_one(
        {"email": email},
        {"$set": {
            "early_bird_sub_id": sub_id,
            "early_bird_plan_key": plan_key,
            "early_bird_payment_link": payment_link,
            "updated_at": int(time.time()),
        }}
    )
    logger.info("Subscription created and stored", extra={"email": email, "sub_id": sub_id, "plan_key": plan_key})
    return {"subscription_id": sub_id, "payment_link": payment_link}


def create_early_bird_sub_link(email: str, plan_key: str, expire_by: int = None) -> dict:
    try:
        email = email.lower()
        logger.info("Early bird subscription link request", extra={"email": email, "plan_key": plan_key})
        user = user_profile.find_one({"email": email})

        if user is None:
            logger.info("New user — creating profile and subscription", extra={"email": email})
            user_profile.insert_one({
                "email": email,
                "chat_history": [],
                "vision_board_url": "",
                "is_paid": False,
                "created_at": int(time.time()),
                "updated_at": int(time.time()),
            })
            return _create_and_store_subscription(email, plan_key, expire_by)

        existing_sub_id = user.get("early_bird_sub_id")

        if not existing_sub_id:
            logger.info("No existing subscription — creating new one", extra={"email": email})
            return _create_and_store_subscription(email, plan_key, expire_by)

        existing_sub = fetch_subscription(existing_sub_id)
        existing_status = existing_sub.get("status")
        existing_plan_key = user.get("early_bird_plan_key")

        logger.info("Existing subscription found", extra={"email": email, "sub_id": existing_sub_id, "status": existing_status, "plan_key": existing_plan_key})

        if existing_status in _PAID_STATUSES:
            logger.warning("Subscription already paid — rejecting new request", extra={"email": email, "status": existing_status})
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Subscription already paid (status: {existing_status}). Cannot create a new one."
            )

        if existing_status in _UNPAID_STATUSES:
            if existing_plan_key == plan_key:
                logger.info("Returning existing unpaid subscription link", extra={"email": email, "sub_id": existing_sub_id})
                return {
                    "subscription_id": existing_sub_id,
                    "payment_link": user.get("early_bird_payment_link", ""),
                }
            logger.info("Plan changed — cancelling existing subscription", extra={"email": email, "old_plan": existing_plan_key, "new_plan": plan_key})
            cancel_subscription(existing_sub_id)

        # existing_status is inactive or was just cancelled above
        return _create_and_store_subscription(email, plan_key, expire_by)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating early bird subscription link", extra={"email": email, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
