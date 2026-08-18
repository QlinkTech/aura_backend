import time
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.services.db.mongo_utils import (
    user_profile, chat_sessions, eft_sessions,
    guided_viz_sessions, journal_log, resources, notifications,
)
# Same resolver the admin user list uses, so the payment buckets reported here
# line up exactly with the `payment_status` filter on GET /users.
from app.routes.system_sub_routes.users import _resolve_payment_status
from app.utils.logger_config import logger

stats_router = APIRouter()

# "This month" follows the IST calendar — the business's local month, not UTC's.
# Fixed offset rather than ZoneInfo("Asia/Kolkata"): India has no DST, and the
# slim runtime image ships no tzdata (same reasoning as gupshup/notifications.py).
_IST = timezone(timedelta(hours=5, minutes=30))

# Statuses that mean real money changed hands at some point. Deliberately wider
# than the "currently paying" set in access_sync.py — this is a "did they ever
# convert" test, so it must survive the subscription later ending.
_EVER_PAID_STATUSES = {"active", "authenticated", "charged", "completed"}


def _avg(total: int, count: int, decimals: int = 2) -> float:
    return round(total / count, decimals) if count else 0


def _month_start_ts() -> int:
    """Epoch seconds at 00:00 IST on the 1st of the current month."""
    now_ist = datetime.now(_IST)
    return int(now_ist.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())


@stats_router.get("/stats")
def get_stats():
    try:
        # ── Users ────────────────────────────────────────────────
        # Every user-level number comes from one pass over the profiles rather
        # than a dozen count_documents() round trips, because the interesting
        # buckets (resolved payment status, "ever converted") are derived from
        # several fields at once and can't be expressed as a plain Mongo filter.
        now_ts       = int(time.time())
        month_start  = _month_start_ts()

        total_users = total_paid = 0
        new_this_month = link_generated_not_paid = 0
        active_subscriptions = granted_access = 0
        cancelled_users = halted_users = 0
        trial_active = trial_expired = unconverted = 0
        sub_status_breakdown: dict = {}
        payment_status_breakdown: dict = {}

        for doc in user_profile.find({}, {
            "is_paid": 1, "is_bypassed": 1, "subscription_status": 1,
            "early_bird_sub_id": 1, "trial_end_at": 1, "paid_until": 1, "created_at": 1,
        }):
            total_users += 1

            sub_status   = doc.get("subscription_status")
            is_bypassed  = bool(doc.get("is_bypassed"))
            trial_end_at = doc.get("trial_end_at") or 0
            # "Did they ever actually pay", not "are they paying now" — a paid_until
            # in the past still means a real payment happened.
            ever_paid    = bool(doc.get("paid_until")) or sub_status in _EVER_PAID_STATUSES

            if doc.get("is_paid"):
                total_paid += 1
            if (doc.get("created_at") or 0) >= month_start:
                new_this_month += 1
            if doc.get("early_bird_sub_id") and not doc.get("is_paid"):
                link_generated_not_paid += 1

            sub_status_breakdown[sub_status or "no_subscription"] = (
                sub_status_breakdown.get(sub_status or "no_subscription", 0) + 1
            )

            resolved = _resolve_payment_status(doc)
            payment_status_breakdown[resolved] = payment_status_breakdown.get(resolved, 0) + 1

            if resolved == "active":
                active_subscriptions += 1
            if is_bypassed:
                granted_access += 1
            if sub_status == "cancelled":
                cancelled_users += 1
            if sub_status == "halted":
                halted_users += 1

            # A free trial is a trial_end_at window with no payment behind it —
            # both the "free" plan and any trial that ran before a conversion.
            if trial_end_at and not ever_paid:
                if now_ts < trial_end_at:
                    trial_active += 1
                else:
                    trial_expired += 1

            # Unconverted: signed up, never paid, and not manually granted access.
            # Includes people who never started a trial at all.
            if not ever_paid and not is_bypassed:
                unconverted += 1

        total_unpaid = total_users - total_paid

        # ── Chat ─────────────────────────────────────────────────
        total_chat_sessions  = chat_sessions.count_documents({})

        chat_agg = list(chat_sessions.aggregate([
            {"$project": {"email": 1, "msg_count": {"$size": {"$ifNull": ["$messages", []]}}}},
            {"$group": {
                "_id": "$email",
                "session_count":  {"$sum": 1},
                "message_count":  {"$sum": "$msg_count"},
            }},
            {"$group": {
                "_id": None,
                "active_users":          {"$sum": 1},
                "total_messages":        {"$sum": "$message_count"},
                "total_sessions":        {"$sum": "$session_count"},
                "avg_sessions_per_user": {"$avg": "$session_count"},
                "avg_messages_per_user": {"$avg": "$message_count"},
            }}
        ]))
        chat_agg = chat_agg[0] if chat_agg else {}

        chat_active_users = chat_agg.get("active_users", 0)
        chat_total_msgs   = chat_agg.get("total_messages", 0)

        avg_msgs_per_session = _avg(
            chat_total_msgs,
            total_chat_sessions,
        )

        most_active_result = list(chat_sessions.aggregate([
            {"$project": {"email": 1, "msg_count": {"$size": {"$ifNull": ["$messages", []]}}}},
            {"$group": {"_id": "$email", "total_messages": {"$sum": "$msg_count"}, "session_count": {"$sum": 1}}},
            {"$sort": {"total_messages": -1}},
            {"$limit": 1},
        ]))
        most_active_user = None
        if most_active_result:
            top      = most_active_result[0]
            user_doc = user_profile.find_one({"email": top["_id"]}, {"_id": 0, "username": 1})
            most_active_user = {
                "email":          top["_id"],
                "username":       user_doc.get("username", "") if user_doc else "",
                "total_messages": top["total_messages"],
                "session_count":  top["session_count"],
            }

        # ── EFT Tapping ──────────────────────────────────────────
        total_eft      = eft_sessions.count_documents({})
        completed_eft  = eft_sessions.count_documents({"is_complete": True})

        eft_agg = list(eft_sessions.aggregate([
            {"$group": {"_id": "$email", "session_count": {"$sum": 1}}},
            {"$group": {
                "_id": None,
                "active_users":          {"$sum": 1},
                "avg_sessions_per_user": {"$avg": "$session_count"},
            }}
        ]))
        eft_agg = eft_agg[0] if eft_agg else {}

        # ── Guided Visualization ─────────────────────────────────
        total_gv     = guided_viz_sessions.count_documents({})
        completed_gv = guided_viz_sessions.count_documents({"is_complete": True})
        errored_gv   = guided_viz_sessions.count_documents({"error": True})

        gv_agg = list(guided_viz_sessions.aggregate([
            {"$group": {"_id": "$email", "session_count": {"$sum": 1}}},
            {"$group": {
                "_id": None,
                "active_users":          {"$sum": 1},
                "avg_sessions_per_user": {"$avg": "$session_count"},
            }}
        ]))
        gv_agg = gv_agg[0] if gv_agg else {}

        # ── Vision Board ─────────────────────────────────────────
        # Boards live on the user profile as `vision_board_url`, which doubles
        # as the status field: "" / missing = never started, "preparing" =
        # generation queued, "failed" = generation errored, anything else is
        # the Cloudinary URL of a finished board. One board per user (the
        # upload public_id is per-email), so counts are also user counts.
        vb_counts = {
            doc["_id"]: doc["count"]
            for doc in user_profile.aggregate([
                {"$project": {
                    "status": {
                        "$let": {
                            "vars": {"url": {"$ifNull": ["$vision_board_url", ""]}},
                            "in": {"$switch": {
                                "branches": [
                                    {"case": {"$eq": ["$$url", ""]},          "then": "not_started"},
                                    {"case": {"$eq": ["$$url", "preparing"]}, "then": "preparing"},
                                    {"case": {"$eq": ["$$url", "failed"]},    "then": "failed"},
                                ],
                                "default": "generated",
                            }},
                        }
                    }
                }},
                {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            ])
        }

        generated_vb   = vb_counts.get("generated", 0)
        preparing_vb   = vb_counts.get("preparing", 0)
        failed_vb      = vb_counts.get("failed", 0)
        not_started_vb = vb_counts.get("not_started", 0)

        # ── Journal ───────────────────────────────────────────────
        total_journal = journal_log.count_documents({})

        journal_agg = list(journal_log.aggregate([
            {"$group": {"_id": "$email", "entry_count": {"$sum": 1}}},
            {"$group": {
                "_id": None,
                "active_users":        {"$sum": 1},
                "avg_entries_per_user": {"$avg": "$entry_count"},
                "max_entries":         {"$max": "$entry_count"},
            }}
        ]))
        journal_agg = journal_agg[0] if journal_agg else {}

        # ── Resources ─────────────────────────────────────────────
        resources_by_category = {
            doc["_id"]: doc["count"]
            for doc in resources.aggregate([
                {"$group": {"_id": "$category", "count": {"$sum": 1}}}
            ])
        }
        total_resources = sum(resources_by_category.values())

        # ── Notifications ─────────────────────────────────────────
        total_notifs  = notifications.count_documents({})
        total_unread  = notifications.count_documents({"is_read": False})
        total_read    = total_notifs - total_unread

        notifs_by_type = {
            doc["_id"]: doc["count"]
            for doc in notifications.aggregate([
                {"$group": {"_id": "$type", "count": {"$sum": 1}}}
            ])
        }

        return {
            "users": {
                "total":                   total_users,
                "new_this_month":          new_this_month,
                "active_subscriptions":    active_subscriptions,
                "cancelled":               cancelled_users,
                "halted":                  halted_users,
                "granted_access":          granted_access,
                "free_trial_active":       trial_active,
                "free_trial_expired":      trial_expired,
                "unconverted":             unconverted,
                "unpaid":                  total_unpaid,
                "link_generated_not_paid": link_generated_not_paid,
                "subscription_breakdown":  sub_status_breakdown,
                "payment_status_breakdown": payment_status_breakdown,
            },
            "features": {
                "chat": {
                    "total_sessions":           total_chat_sessions,
                    "total_messages":           chat_total_msgs,
                    "active_users":             chat_active_users,
                    "avg_sessions_per_user":    round(chat_agg.get("avg_sessions_per_user", 0), 2),
                    "avg_messages_per_user":    round(chat_agg.get("avg_messages_per_user", 0), 2),
                    "avg_messages_per_session": avg_msgs_per_session,
                    "most_active_user":         most_active_user,
                },
                "eft_tapping": {
                    "total_sessions":        total_eft,
                    "completed_sessions":    completed_eft,
                    "pending_sessions":      total_eft - completed_eft,
                    "completion_rate_%":     _avg(completed_eft * 100, total_eft, 1),
                    "active_users":          eft_agg.get("active_users", 0),
                    "avg_sessions_per_user": round(eft_agg.get("avg_sessions_per_user", 0), 2),
                },
                "guided_visualization": {
                    "total_sessions":        total_gv,
                    "completed_sessions":    completed_gv,
                    "errored_sessions":      errored_gv,
                    "pending_sessions":      total_gv - completed_gv - errored_gv,
                    "completion_rate_%":     _avg(completed_gv * 100, total_gv, 1),
                    "active_users":          gv_agg.get("active_users", 0),
                    "avg_sessions_per_user": round(gv_agg.get("avg_sessions_per_user", 0), 2),
                },
                "vision_board": {
                    "total_generated": generated_vb,
                    "preparing":       preparing_vb,
                    "failed":          failed_vb,
                    "not_started":     not_started_vb,
                    "adoption_rate_%": _avg(generated_vb * 100, total_users, 1),
                    "success_rate_%":  _avg(generated_vb * 100, generated_vb + failed_vb, 1),
                },
                "journal": {
                    "total_entries":        total_journal,
                    "active_users":         journal_agg.get("active_users", 0),
                    "avg_entries_per_user": round(journal_agg.get("avg_entries_per_user", 0), 2),
                    "max_entries_by_user":  journal_agg.get("max_entries", 0),
                },
                "resources": {
                    "total":       total_resources,
                    "by_category": resources_by_category,
                },
                "notifications": {
                    "total_sent":    total_notifs,
                    "total_read":    total_read,
                    "total_unread":  total_unread,
                    "read_rate_%":   _avg(total_read * 100, total_notifs, 1),
                    "by_type":       notifs_by_type,
                },
            },
        }

    except Exception as e:
        logger.error("System: error fetching stats", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)
