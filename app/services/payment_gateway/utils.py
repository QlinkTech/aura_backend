import time
from fastapi import HTTPException, status
from app.services.db.mongo_utils import user_profile
from app.services.payment_gateway.client import create_subscription, cancel_subscription, pause_subscription, fetch_subscription
from app.utils.logger_config import logger

FREE_PLAN_DURATION_DAYS = 30

# Subscription is active/paid — do not allow new subscription
_PAID_STATUSES = {"active", "pending", "halted", "completed", "authenticated"}
# Subscription was created but user hasn't paid yet — allow plan switch
_UNPAID_STATUSES = {"created"}

def _create_and_store_subscription(email: str, plan_key: str, expire_by: int = None) -> dict:
    logger.info("Creating subscription", extra={"email": email, "plan_key": plan_key})

    subscription = create_subscription(
        plan_key=plan_key,
        notify_email=email,
        expire_by=expire_by,
        start_at=None,
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
                "username": "", 
                "chat_history": [],
                "vision_board_url": "",
                "is_paid": False,
                "created_at": int(time.time()),
                "updated_at": int(time.time()),
                "is_logged_in": False
            })
            return _create_and_store_subscription(email, plan_key, expire_by)

        existing_sub_id = user.get("early_bird_sub_id")

        if not existing_sub_id:
            logger.info("No existing subscription — creating new one", extra={"email": email})
            return _create_and_store_subscription(email, plan_key, expire_by)

        try:
            existing_sub = fetch_subscription(existing_sub_id)
        except HTTPException:
            logger.warning("Existing sub_id not found on Razorpay — creating new one", extra={"email": email, "sub_id": existing_sub_id})
            return _create_and_store_subscription(email, plan_key, expire_by)

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


def create_sub_link(email: str, plan_key: str, expire_by: int = None) -> dict:
    """Create a subscription link for an existing user only. Raises 404 if user not found."""
    try:
        email = email.lower()
        logger.info("Subscription link request", extra={"email": email, "plan_key": plan_key})
        user = user_profile.find_one({"email": email})

        if user is None:
            logger.warning("Subscription request for non-existent user", extra={"email": email})
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        existing_sub_id = user.get("early_bird_sub_id")

        if not existing_sub_id:
            return _create_and_store_subscription(email, plan_key, expire_by)

        try:
            existing_sub = fetch_subscription(existing_sub_id)
        except HTTPException:
            logger.warning("Existing sub_id not found on Razorpay — creating new one", extra={"email": email, "sub_id": existing_sub_id})
            return _create_and_store_subscription(email, plan_key, expire_by)

        existing_status = existing_sub.get("status")
        existing_plan_key = user.get("early_bird_plan_key")

        logger.info("Existing subscription found", extra={"email": email, "sub_id": existing_sub_id, "status": existing_status})

        if existing_status in _PAID_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Subscription already active (status: {existing_status})."
            )

        if existing_status in _UNPAID_STATUSES and existing_plan_key == plan_key:
            return {
                "subscription_id": existing_sub_id,
                "payment_link": user.get("early_bird_payment_link", ""),
            }

        if existing_status in _UNPAID_STATUSES:
            cancel_subscription(existing_sub_id)

        return _create_and_store_subscription(email, plan_key, expire_by)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating subscription link", extra={"email": email, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


def get_user_subscription(email: str) -> dict:
    try:
        email = email.lower()
        logger.info("Fetching subscription details", extra={"email": email})
        user = user_profile.find_one(
            {"email": email},
            {"early_bird_sub_id": 1, "early_bird_plan_key": 1, "subscription_status": 1, "is_paid": 1}
        )
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        sub_id = user.get("early_bird_sub_id")
        if not sub_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No subscription found for this user")
        sub = fetch_subscription(sub_id)
        return {
            "subscription_id": sub_id,
            "plan_key": user.get("early_bird_plan_key"),
            "status": sub.get("status"),
            "is_paid": user.get("is_paid", False),
            "current_start": sub.get("current_start"),
            "current_end": sub.get("current_end"),
            "charge_at": sub.get("charge_at"),
            "paid_count": sub.get("paid_count"),
            "remaining_count": sub.get("remaining_count"),
            "total_count": sub.get("total_count"),
            "short_url": sub.get("short_url"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching subscription details", extra={"email": email, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def _get_active_subscription_id(email: str) -> str:
    user = user_profile.find_one({"email": email}, {"early_bird_sub_id": 1, "subscription_status": 1})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    sub_id = user.get("early_bird_sub_id")
    if not sub_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No subscription found for this user")
    sub_status = user.get("subscription_status", "")
    if sub_status not in ("active", "authenticated"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Subscription is not active (current status: {sub_status})"
        )
    return sub_id


def cancel_user_subscription(email: str, cancel_at_cycle_end: bool = False) -> dict:
    try:
        email = email.lower()
        logger.info("Cancel subscription request", extra={"email": email, "cancel_at_cycle_end": cancel_at_cycle_end})
        sub_id = _get_active_subscription_id(email)
        result = cancel_subscription(sub_id, cancel_at_cycle_end=1 if cancel_at_cycle_end else 0)
        logger.info("Subscription cancelled", extra={"email": email, "sub_id": sub_id})
        return {"message": "Subscription cancelled successfully", "subscription_id": sub_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error cancelling subscription", extra={"email": email, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def activate_free_plan(email: str) -> dict:
    try:
        email = email.lower()
        logger.info("Free plan activation request", extra={"email": email})
        user = user_profile.find_one({"email": email})

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if user.get("subscription_status") == "free":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Free plan has already been activated for this account"
            )

        # Block anyone who has ever had an active/paid subscription (cancelled, halted, completed, etc.)
        # Allow if sub was created but never paid (status: "created")
        if user.get("early_bird_sub_id") and user.get("subscription_status") not in (None, "", "created"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Free plan is only available for new accounts with no prior subscription"
            )

        now = int(time.time())
        trial_end_at = now + FREE_PLAN_DURATION_DAYS * 24 * 60 * 60
        user_profile.update_one(
            {"email": email},
            {"$set": {
                "is_paid": True,
                "subscription_status": "free",
                "trial_end_at": trial_end_at,
                "updated_at": now,
            }}
        )
        logger.info("Free plan activated", extra={"email": email, "trial_end_at": trial_end_at})
        return {"message": "Free plan activated successfully", "expires_at": trial_end_at}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error activating free plan", extra={"email": email, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def pause_user_subscription(email: str) -> dict:
    try:
        email = email.lower()
        logger.info("Pause subscription request", extra={"email": email})
        sub_id = _get_active_subscription_id(email)
        result = pause_subscription(sub_id)
        logger.info("Subscription paused", extra={"email": email, "sub_id": sub_id})
        return {"message": "Subscription paused successfully", "subscription_id": sub_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error pausing subscription", extra={"email": email, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
