import time
from fastapi import HTTPException, status
from app.utils.db.mongo_utils import user_profile
from app.services.payment_gateway.client import create_subscription, cancel_subscription, fetch_subscription

# Subscription is active/paid — do not allow new subscription
_PAID_STATUSES = {"active", "pending", "halted", "completed"}
# Subscription was created but user hasn't paid yet — allow plan switch
_UNPAID_STATUSES = {"created", "authenticated"}

def _create_and_store_subscription(email: str, plan_key: str, expire_by: int = None) -> dict:
    subscription = create_subscription(
        plan_key=plan_key,
        notify_email=email,
        expire_by=expire_by,
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
    return {"subscription_id": sub_id, "payment_link": payment_link}


def create_early_bird_sub_link(email: str, plan_key: str, expire_by: int = None) -> dict:
    try:
        email = email.lower()
        user = user_profile.find_one({"email": email})

        if user is None:
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
            return _create_and_store_subscription(email, plan_key, expire_by)

        existing_sub = fetch_subscription(existing_sub_id)
        existing_status = existing_sub.get("status")
        existing_plan_key = user.get("early_bird_plan_key")

        if existing_status in _PAID_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Subscription already paid (status: {existing_status}). Cannot create a new one."
            )

        if existing_status in _UNPAID_STATUSES:
            if existing_plan_key == plan_key:
                return {
                    "subscription_id": existing_sub_id,
                    "payment_link": user.get("early_bird_payment_link", ""),
                }
            cancel_subscription(existing_sub_id)

        # existing_status is inactive or was just cancelled above
        return _create_and_store_subscription(email, plan_key, expire_by)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

