import time
from pymongo import MongoClient
from app.utils.env_load import mongodb_uri

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


def save_payment_failed(payment: dict):
    payment_id = payment.get("id")
    email = payment.get("email", "").lower()

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

    status_map = {
        "subscription.activated": "active",
        "subscription.charged": "active",
        "subscription.cancelled": "cancelled",
        "subscription.completed": "completed",
        "subscription.halted": "halted",
    }
    resolved_status = status_map.get(event, event)
    is_paid = event in ("subscription.activated", "subscription.charged")

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
