import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException, status
from app.utils.env_load import razorpay_webhook_secret
from app.utils.db.razorpay_utils import (
    save_payment_captured,
    save_payment_failed,
    save_subscription_event,
)

payment_router = APIRouter()

SUBSCRIPTION_EVENTS = {
    "subscription.activated",
    "subscription.charged",
    "subscription.cancelled",
    "subscription.completed",
    "subscription.halted",
}


def _verify_signature(body: bytes, signature: str) -> bool:
    expected = hmac.new(
        razorpay_webhook_secret.encode("utf-8"),
        body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@payment_router.post("/webhook")
async def razorpay_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not _verify_signature(body, signature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature"
        )

    payload = await request.json()
    event = payload.get("event")
    entity = payload.get("payload", {})

    if event == "payment.captured":
        payment = entity.get("payment", {}).get("entity", {})
        save_payment_captured(payment)

    elif event == "payment.failed":
        payment = entity.get("payment", {}).get("entity", {})
        save_payment_failed(payment)

    elif event in SUBSCRIPTION_EVENTS:
        subscription = entity.get("subscription", {}).get("entity", {})
        save_subscription_event(event, subscription)

    return {"status": "ok"}
