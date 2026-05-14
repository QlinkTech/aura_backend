from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.services.db.mongo_utils import (
    user_profile, chat_sessions, eft_sessions,
    guided_viz_sessions, journal_log, resources, notifications,
)
from app.utils.logger_config import logger

stats_router = APIRouter()


def _avg(total: int, count: int, decimals: int = 2) -> float:
    return round(total / count, decimals) if count else 0


@stats_router.get("/stats")
def get_stats():
    try:
        # ── Users ────────────────────────────────────────────────
        total_users  = user_profile.count_documents({})
        total_paid   = user_profile.count_documents({"is_paid": True})
        total_unpaid = total_users - total_paid

        link_generated_not_paid = user_profile.count_documents({
            "early_bird_sub_id": {"$exists": True},
            "is_paid": False,
        })

        sub_status_breakdown = {
            doc["_id"]: doc["count"]
            for doc in user_profile.aggregate([
                {"$group": {
                    "_id": {"$ifNull": ["$subscription_status", "no_subscription"]},
                    "count": {"$sum": 1},
                }}
            ])
        }

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
                "paid":                    total_paid,
                "unpaid":                  total_unpaid,
                "link_generated_not_paid": link_generated_not_paid,
                "subscription_breakdown":  sub_status_breakdown,
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
