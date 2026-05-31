import time
from app.utils.logger_config import logger
from app.services.db.mongo_utils import user_profile, payments
from app.services.brevo.client import (
    send_welcome_email, send_thank_you_email,
    send_subscription_cancelled_email,
    add_subscribed_contact, add_cancelled_contact, add_halted_contact, add_trial_contact,
    remove_contact_from_list, LIST_SUBSCRIBED, LIST_CANCELLED, LIST_HALTED, LIST_TRIAL,
)



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
        "subscription.authenticated": "active",
        "subscription.activated": "active",
        "subscription.charged": "active",
        "subscription.completed": "completed",
        "subscription.updated": "active",
        "subscription.cancelled": "cancelled",
        "subscription.halted": "halted",
        "subscription.pending": "pending",
        "subscription.paused": "paused",
        "subscription.resumed": "active",
    }
    resolved_status = status_map.get(event, event)
    is_paid = event in (
        "subscription.authenticated",
        "subscription.activated",
        "subscription.charged",
        "subscription.resumed",
        "subscription.pending",  # keep access during retry window, revoke only on halted
    )

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

    # Match by subscription_id first — the webhook email can differ from the signup email
    # (e.g. user types a different email during UPI checkout)
    profile = None
    if subscription_id:
        profile = user_profile.find_one({"early_bird_sub_id": subscription_id})
    if profile is None and email:
        profile = user_profile.find_one({"email": email})

    if profile:
        effective_is_paid = is_paid
        if event in ("subscription.cancelled", "subscription.paused"):
            trial_end_at = profile.get("trial_end_at", 0)
            effective_is_paid = int(time.time()) < trial_end_at

        update_fields = {
            "subscription_status": resolved_status,
            "is_paid": effective_is_paid,
            "updated_at": int(time.time()),
        }
        # Keep early_bird_sub_id pointing to the active subscription
        if effective_is_paid:
            update_fields["early_bird_sub_id"] = subscription_id

        user_profile.update_one({"_id": profile["_id"]}, {"$set": update_fields})
        logger.info("User profile updated for subscription event", extra={"event": event, "email": email, "resolved_status": resolved_status, "is_paid": is_paid})

        if event == "subscription.authenticated" and email:
            try:
                username = profile.get("username", "")
                send_welcome_email(to_email=email, to_name=username)
                logger.info("Welcome email sent", extra={"email": email})
            except Exception as e:
                logger.error("Failed to send welcome email", extra={"email": email, "error": str(e)})

        if event == "subscription.charged" and email:
            try:
                username = profile.get("username", "")
                send_thank_you_email(to_email=email, to_name=username)
                logger.info("Thank you email sent", extra={"email": email})
            except Exception as e:
                logger.error("Failed to send thank you email", extra={"email": email, "error": str(e)})

        if event in ("subscription.authenticated", "subscription.activated", "subscription.charged", "subscription.resumed") and email:
            try:
                remove_contact_from_list(email=email, list_id=LIST_CANCELLED)
                remove_contact_from_list(email=email, list_id=LIST_HALTED)
            except Exception as e:
                logger.error("Failed to remove from cancelled/halted lists", extra={"email": email, "error": str(e)})

        if event in ("subscription.activated", "subscription.charged", "subscription.resumed") and email:
            try:
                username = profile.get("username", "")
                add_subscribed_contact(email=email, name=username)
                logger.info("Contact added to subscribed list", extra={"email": email})
            except Exception as e:
                logger.error("Failed to add to subscribed list", extra={"email": email, "error": str(e)})

        if event == "subscription.cancelled" and email:
            try:
                username = profile.get("username", "")
                add_cancelled_contact(email=email, name=username)
                remove_contact_from_list(email=email, list_id=LIST_SUBSCRIBED)
                send_subscription_cancelled_email(to_email=email, to_name=username)
                logger.info("Contact moved to cancelled list", extra={"email": email})
            except Exception as e:
                logger.error("Failed to update cancelled contact lists", extra={"email": email, "error": str(e)})

        if event == "subscription.halted" and email:
            try:
                username = profile.get("username", "")
                add_halted_contact(email=email, name=username)
                remove_contact_from_list(email=email, list_id=LIST_SUBSCRIBED)
                logger.info("Contact moved to halted list", extra={"email": email})
            except Exception as e:
                logger.error("Failed to move contact to halted list", extra={"email": email, "error": str(e)})

        if email:
            try:
                trial_end_at = profile.get("trial_end_at", 0)
                in_trial = bool(effective_is_paid and trial_end_at and int(time.time()) < trial_end_at)
                username = profile.get("username", "")
                if in_trial:
                    add_trial_contact(email=email, name=username)
                else:
                    remove_contact_from_list(email=email, list_id=LIST_TRIAL)
            except Exception as e:
                logger.error("Failed to update trial list", extra={"email": email, "error": str(e)})
    else:
        logger.warning("No user profile found for subscription event", extra={"event": event, "subscription_id": subscription_id, "email": email})
