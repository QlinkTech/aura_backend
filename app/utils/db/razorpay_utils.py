from datetime import datetime
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
        "created_at": datetime.utcnow()
    })

    if email:
        user_profile.update_one(
            {"email": email},
            {"$set": {"is_paid": True, "updated_at": datetime.utcnow()}}
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
        "created_at": datetime.utcnow()
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
            "updated_at": datetime.utcnow(),
        }, "$setOnInsert": {
            "created_at": datetime.utcnow(),
        }},
        upsert=True
    )

    if email:
        user_profile.update_one(
            {"email": email},
            {"$set": {
                "subscription_status": resolved_status,
                "is_paid": is_paid,
                "updated_at": datetime.utcnow()
            }}
        )
