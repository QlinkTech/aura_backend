"""
Quick test for the daily scheduler jobs (subscription_reconcile + access_sync).
Run from project root: python test_scheduler_jobs.py

- reconcile_pending_subscriptions is tested against a real Mongo doc (uses the
  MONGO_URI in .env) but with fetch_subscription mocked, so it never calls Razorpay.
  A throwaway test user is inserted and deleted automatically.
- sync_access_status's logic is tested via its pure helpers (_compute_is_paid /
  _is_orphaned_grant) with in-memory dicts only — it is NOT run for real here,
  since it scans the entire user_profile collection unfiltered and would touch
  every live user in whatever DB your .env points to.
"""
import time
from unittest.mock import patch

from app.services.db.mongo_utils import user_profile
from app.services.payment_gateway import subscription_reconcile
from app.services.payment_gateway.access_sync import _compute_is_paid, _is_orphaned_grant

TEST_EMAIL = "test_reconcile_job@example.com"


def test_reconcile_pending_subscriptions():
    print("\n--- reconcile_pending_subscriptions ---")
    user_profile.delete_many({"email": TEST_EMAIL})
    user_profile.insert_one({
        "email": TEST_EMAIL,
        "early_bird_sub_id": "sub_fake_test_id",
        "created_at": int(time.time()),
    })

    with patch.object(subscription_reconcile, "fetch_subscription", return_value={"status": "expired"}):
        subscription_reconcile.reconcile_pending_subscriptions()

    doc = user_profile.find_one({"email": TEST_EMAIL})
    assert doc["subscription_status"] == "expired", f"expected 'expired', got {doc.get('subscription_status')!r}"
    print("PASS: subscription_status backfilled to 'expired'")

    user_profile.delete_many({"email": TEST_EMAIL})


def test_compute_is_paid():
    print("\n--- access_sync._compute_is_paid ---")
    now = int(time.time())

    cases = [
        ("not paid, active trial -> True", {"is_paid": False, "trial_end_at": now + 1000}, True),
        ("not paid, active sub status -> True", {"is_paid": False, "subscription_status": "active"}, True),
        ("not paid, nothing -> False", {"is_paid": False}, False),
        ("paid, lapsed status past trial_end -> False", {"is_paid": True, "subscription_status": "cancelled", "trial_end_at": now - 1000}, False),
        ("paid, lapsed status but trial still running -> True", {"is_paid": True, "subscription_status": "cancelled", "trial_end_at": now + 1000}, True),
        ("paid, orphaned grant -> False", {"is_paid": True}, False),
        ("paid, legit active -> True", {"is_paid": True, "subscription_status": "active"}, True),
    ]
    for label, doc, expected in cases:
        result = _compute_is_paid(doc, now)
        status = "PASS" if result == expected else "FAIL"
        print(f"{status}: {label} -> {result}")
        assert result == expected, label


def test_is_orphaned_grant():
    print("\n--- access_sync._is_orphaned_grant ---")
    assert _is_orphaned_grant({}) is True
    assert _is_orphaned_grant({"subscription_status": "active"}) is False
    assert _is_orphaned_grant({"trial_end_at": 123}) is False
    assert _is_orphaned_grant({"early_bird_sub_id": "sub_x"}) is False
    print("PASS: all cases")


if __name__ == "__main__":
    test_reconcile_pending_subscriptions()
    test_compute_is_paid()
    test_is_orphaned_grant()
    print("\nAll tests passed.")
