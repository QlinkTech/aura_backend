"""
One-time migration: sync existing users into the correct Brevo lists.

PARKED — will not run as-is. The Brevo contact-list code this depends on is
commented out in app/services/mail/client.py (Resend migration); uncomment it
there before running this again.

List rules:
  #3  subscribed  — is_paid = true
  #8  cancelled   — subscription_status = cancelled
  #9  halted      — subscription_status = halted
  #10 trial       — now < trial_end_at (regardless of paid/cancelled status)

A user can be in multiple lists simultaneously, e.g.:
  trial_active + cancelled → #8 + #10
  trial_active + paid      → #3 + #10

Run from project root:
    python -m scripts.reconfigure_brevo_lists [--dry-run]
"""

import time
import argparse
from app.services.db.mongo_utils import user_profile
from app.services.brevo.client import (
    add_contact_to_list, remove_contact_from_list,
    LIST_SUBSCRIBED, LIST_CANCELLED, LIST_HALTED, LIST_TRIAL,
)

LIST_NAMES = {
    LIST_SUBSCRIBED: "subscribed(#3)",
    LIST_CANCELLED:  "cancelled(#8)",
    LIST_HALTED:     "halted(#9)",
    LIST_TRIAL:      "trial(#10)",
}


def resolve_lists(user: dict):
    """Returns (add_to, remove_from) as lists of list IDs."""
    is_paid    = user.get("is_paid", False)
    sub_status = user.get("subscription_status")
    trial_end_at = user.get("trial_end_at", 0)
    # trial_active: matches users.py _resolve_payment_status exactly
    in_trial = bool(
        is_paid and sub_status == "cancelled"
        and trial_end_at and int(time.time()) < trial_end_at
    )

    add_to     = set()
    remove_from = set()

    if is_paid and sub_status != "cancelled":
        # Active paid / granted access — in subscribed, not cancelled
        add_to.add(LIST_SUBSCRIBED)
        remove_from.add(LIST_CANCELLED)
    elif in_trial:
        # Cancelled mid-trial — in both trial and cancelled, not subscribed
        add_to.add(LIST_TRIAL)
        add_to.add(LIST_CANCELLED)
        remove_from.add(LIST_SUBSCRIBED)
    elif sub_status == "cancelled":
        # Cancelled, trial expired — only cancelled
        add_to.add(LIST_CANCELLED)
        remove_from.add(LIST_SUBSCRIBED)
        remove_from.add(LIST_TRIAL)
    else:
        remove_from.update({LIST_SUBSCRIBED, LIST_CANCELLED, LIST_TRIAL})

    if sub_status == "halted":
        add_to.add(LIST_HALTED)
        remove_from.discard(LIST_HALTED)
    else:
        remove_from.add(LIST_HALTED)

    remove_from -= add_to  # never remove what we're also adding
    return list(add_to), list(remove_from)


def reconfigure(dry_run: bool = False):
    query = {"$or": [
        {"is_paid": True},
        {"subscription_status": {"$in": ["cancelled", "halted", "active", "authenticated", "charged"]}},
        {"trial_end_at": {"$exists": True}},
    ]}

    users = list(user_profile.find(query, {
        "_id": 0, "email": 1, "username": 1,
        "is_paid": 1, "subscription_status": 1, "trial_end_at": 1,
    }))

    print(f"Found {len(users)} user(s) to process{'  [DRY RUN]' if dry_run else ''}.\n")

    updated = skipped = errors = 0

    for user in users:
        email = user.get("email", "")
        name  = user.get("username", "")

        if not email:
            print(f"  SKIP  (no email)")
            skipped += 1
            continue

        add_to, remove_from = resolve_lists(user)
        add_names    = [LIST_NAMES[l] for l in add_to]
        remove_names = [LIST_NAMES[l] for l in remove_from]

        print(f"  {email}")
        print(f"    add={add_names}  remove={remove_names}")

        if not dry_run:
            ok = True
            for list_id in add_to:
                try:
                    add_contact_to_list(email=email, name=name, list_id=list_id)
                except Exception as e:
                    print(f"    ERROR adding to {LIST_NAMES[list_id]}: {e}")
                    ok = False
            for list_id in remove_from:
                try:
                    remove_contact_from_list(email=email, list_id=list_id)
                except Exception as e:
                    print(f"    ERROR removing from {LIST_NAMES[list_id]}: {e}")
                    ok = False
            if ok:
                updated += 1
            else:
                errors += 1
        else:
            updated += 1

    print(f"\nDone. updated={updated}  skipped={skipped}  errors={errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview without touching Brevo")
    args = parser.parse_args()
    reconfigure(dry_run=args.dry_run)
