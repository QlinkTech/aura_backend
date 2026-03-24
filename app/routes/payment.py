import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException, status, Security
from fastapi.security import APIKeyHeader
from app.utils.env_load import razorpay_webhook_secret, admin_api_key
from app.utils.db.razorpay_utils import (
    save_payment_captured,
    save_payment_failed,
    save_subscription_event,
)
from app.utils.schema import EarlyBirdSubRequest
from app.services.payment_gateway.utils import create_early_bird_sub_link
from app.utils.logger_config import logger

_api_key_header = APIKeyHeader(name="X-API-Key")

def _verify_api_key(key: str = Security(_api_key_header)):
    if key != admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key"
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


@payment_router.post("/early-bird-subscription", dependencies=[Security(_verify_api_key)])
async def early_bird_subscription(request: EarlyBirdSubRequest):
    return create_early_bird_sub_link(
        email=request.email,
        plan_key=request.plan_key,
        expire_by=request.expire_by,
    )


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
    logger.info("Recevied Webhook Data", extra={"data": payload})
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
