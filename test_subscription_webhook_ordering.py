"""
Regression tests for the subscription/payment webhook reconciliation bug:
a subscription.cancelled webhook (e.g. from cancel-at-cycle-end) landing before
a later legitimate payment.captured for the same subscription must not leave the
user's profile stuck on "cancelled" with is_paid=False.

Run from project root: python test_subscription_webhook_ordering.py

Uses a throwaway test user/subscription id in the real Mongo (MONGO_URI from
.env), with all Razorpay API calls mocked — no live network calls, no live
Razorpay data touched.
"""
import time
from unittest.mock import patch

from fastapi import HTTPException

from app.services.db.mongo_utils import user_profile, payments
from app.services.db import razorpay_utils
from app.services.payment_gateway.access_sync import _compute_is_paid
from app.services import auth_service

TEST_EMAIL = "test_webhook_ordering@example.com"
TEST_SUB_ID = "sub_test_webhook_ordering"


def _reset():
    user_profile.delete_many({"email": TEST_EMAIL})
    payments.delete_many({"subscription_id": TEST_SUB_ID})
    payments.delete_many({"email": TEST_EMAIL})


def test_capture_reconciles_stale_cancelled_status():
    """The original bug: subscription.cancelled lands, then a later payment.captured
    for the same subscription arrives — the profile must come out of 'cancelled'."""
    print("\n--- save_payment_captured reconciles a stale cancelled status ---")
    _reset()
    now = int(time.time())
    user_profile.insert_one({
        "email": TEST_EMAIL,
        "early_bird_sub_id": TEST_SUB_ID,
        "early_bird_plan_key": "3_months_plan",
        "subscription_status": "cancelled",   # stale, set by an earlier cancel-at-cycle-end webhook
        "is_paid": False,
        "created_at": now,
    })

    fake_invoice = {"subscription_id": TEST_SUB_ID}
    fake_subscription = {"status": "active", "current_end": now + 90 * 86400}

    with patch.object(razorpay_utils.gateway_client.invoice, "fetch", return_value=fake_invoice), \
         patch.object(razorpay_utils, "fetch_subscription", return_value=fake_subscription):
        razorpay_utils.save_payment_captured({
            "id": "pay_test_capture",
            "email": TEST_EMAIL,
            "amount": 360000,
            "currency": "INR",
            "order_id": "order_test",
            "invoice_id": "inv_test",
        })

    doc = user_profile.find_one({"email": TEST_EMAIL})
    assert doc["subscription_status"] == "active", f"expected 'active', got {doc.get('subscription_status')!r}"
    assert doc["is_paid"] is True, f"expected is_paid=True, got {doc.get('is_paid')!r}"
    assert doc["paid_until"] == fake_subscription["current_end"], "paid_until not backfilled from Razorpay"
    print("PASS: capture correctly un-stuck the stale 'cancelled' status")
    _reset()


def test_stale_subscription_event_is_ignored():
    """A subscription.cancelled webhook that's older than the last-applied event
    for that subscription must not overwrite the newer state (out-of-order delivery)."""
    print("\n--- stale/out-of-order subscription webhook is ignored ---")
    _reset()
    user_profile.insert_one({
        "email": TEST_EMAIL,
        "early_bird_sub_id": TEST_SUB_ID,
        "created_at": int(time.time()),
    })

    # newer event applied first
    razorpay_utils.save_subscription_event(
        "subscription.activated",
        {"id": TEST_SUB_ID, "email": TEST_EMAIL, "current_end": int(time.time()) + 90 * 86400},
        event_created_at=2000,
    )
    # then a stale cancelled event, timestamped earlier, arrives late
    razorpay_utils.save_subscription_event(
        "subscription.cancelled",
        {"id": TEST_SUB_ID, "email": TEST_EMAIL},
        event_created_at=1000,
    )

    doc = user_profile.find_one({"email": TEST_EMAIL})
    assert doc["subscription_status"] == "active", f"stale event overwrote newer state: {doc.get('subscription_status')!r}"
    print("PASS: stale cancelled event was ignored, status stayed 'active'")
    _reset()


def test_halted_event_respects_paid_until():
    """subscription.halted must not revoke access while the already-paid-for
    period (current_end) hasn't ended yet — 'won't renew' != 'access ends now'."""
    print("\n--- halted event keeps access until paid_until ---")
    _reset()
    user_profile.insert_one({
        "email": TEST_EMAIL,
        "early_bird_sub_id": TEST_SUB_ID,
        "is_paid": True,
        "created_at": int(time.time()),
    })

    future_end = int(time.time()) + 5 * 86400
    razorpay_utils.save_subscription_event(
        "subscription.halted",
        {"id": TEST_SUB_ID, "email": TEST_EMAIL, "current_end": future_end},
        event_created_at=int(time.time()),
    )

    doc = user_profile.find_one({"email": TEST_EMAIL})
    assert doc["subscription_status"] == "halted"
    assert doc["is_paid"] is True, f"halted revoked access early despite paid_until in the future: {doc.get('is_paid')!r}"
    assert doc["paid_until"] == future_end
    print("PASS: halted status set, but is_paid stayed True through paid_until")

    # access_sync's daily self-heal must agree, or it would undo this within 24h
    result = _compute_is_paid(doc, int(time.time()))
    assert result is True, "access_sync would incorrectly revoke access before paid_until"
    print("PASS: access_sync._compute_is_paid agrees (paid_until still in the future)")
    _reset()


def test_webhook_event_dedup():
    """Duplicate webhook deliveries (Razorpay retries) must not be double-processed."""
    print("\n--- webhook_events unique index rejects duplicate deliveries ---")
    from pymongo.errors import DuplicateKeyError
    from app.services.db.mongo_utils import webhook_events

    key = f"test.event:{TEST_SUB_ID}:1234567890"
    webhook_events.delete_many({"event_key": key})

    webhook_events.insert_one({"event_key": key, "event": "test.event", "received_at": int(time.time())})
    try:
        webhook_events.insert_one({"event_key": key, "event": "test.event", "received_at": int(time.time())})
        raise AssertionError("duplicate webhook event was not rejected")
    except DuplicateKeyError:
        print("PASS: duplicate webhook event correctly rejected")
    finally:
        webhook_events.delete_many({"event_key": key})


if __name__ == "__main__":
    test_capture_reconciles_stale_cancelled_status()
    test_stale_subscription_event_is_ignored()
    test_halted_event_respects_paid_until()
    test_webhook_event_dedup()
    print("\nAll tests passed.")
