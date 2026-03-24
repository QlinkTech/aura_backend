import time
from pymongo import MongoClient
from app.utils.env_load import mongodb_uri
from app.utils.logger_config import logger

mongo_client = MongoClient(mongodb_uri)
db = mongo_client["mmd"]
user_profile = db["user_profile"]
payments = db["payments"]


def save_payment_captured(payment: dict):
    payment_id = payment.get("id")
    email = payment.get("email", "").lower()
    amount = payment.get("amount", 0)   # paise
    currency = payment.get("currency", "INR")
    order_id = payment.get("order_id")

    logger.info("Saving captured payment", extra={"payment_id": payment_id, "email": email, "amount": amount, "currency": currency})

    payments.insert_one({
        "payment_id": payment_id,
        "order_id": order_id,
        "email": email,
        "amount": amount,
        "currency": currency,
        "status": "captured",
        "event": "payment.captured",
        "raw": payment,
        "created_at": int(time.time())
    })

    if email:
        user_profile.update_one(
            {"email": email},
            {"$set": {"is_paid": True, "updated_at": int(time.time())}}
        )
        logger.info("User marked as paid", extra={"email": email})


def save_payment_failed(payment: dict):
    payment_id = payment.get("id")
    email = payment.get("email", "").lower()

    logger.warning("Saving failed payment", extra={"payment_id": payment_id, "email": email})

    payments.insert_one({
        "payment_id": payment_id,
        "email": email,
        "status": "failed",
        "event": "payment.failed",
        "raw": payment,
        "created_at": int(time.time())
    })


def save_subscription_event(event: str, subscription: dict):
    subscription_id = subscription.get("id")
    email = (
        subscription.get("customer_email")
        or subscription.get("email_id")
        or subscription.get("email")
        or ""
    ).lower()

    logger.info("Saving subscription event", extra={"event": event, "subscription_id": subscription_id, "email": email})

    status_map = {
        "subscription.authenticated": "authenticated",
        "subscription.activated": "active",
        "subscription.charged": "active",
        "subscription.cancelled": "cancelled",
        "subscription.completed": "completed",
        "subscription.halted": "halted",
    }
    resolved_status = status_map.get(event, event)
    is_paid = event in ("subscription.authenticated", "subscription.activated", "subscription.charged")

    payments.update_one(
        {"subscription_id": subscription_id},
        {"$set": {
            "email": email,
            "status": resolved_status,
            "event": event,
            "raw": subscription,
            "updated_at": int(time.time()),
        }, "$setOnInsert": {
            "created_at": int(time.time()),
        }},
        upsert=True
    )

    # Try email first, fall back to subscription_id stored on the profile
    profile = None
    if email:
        profile = user_profile.find_one({"email": email})
    if profile is None and subscription_id:
        profile = user_profile.find_one({"early_bird_sub_id": subscription_id})

    if profile:
        update_fields = {
            "subscription_status": resolved_status,
            "is_paid": is_paid,
            "updated_at": int(time.time()),
        }
        # Keep early_bird_sub_id pointing to the active subscription
        if is_paid:
            update_fields["early_bird_sub_id"] = subscription_id

        user_profile.update_one({"_id": profile["_id"]}, {"$set": update_fields})
        logger.info("User profile updated for subscription event", extra={"event": event, "email": email, "resolved_status": resolved_status, "is_paid": is_paid})
    else:
        logger.warning("No user profile found for subscription event", extra={"event": event, "subscription_id": subscription_id, "email": email})
