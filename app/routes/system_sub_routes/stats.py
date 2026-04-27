from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.services.db.mongo_utils import user_profile, chat_sessions
from app.utils.logger_config import logger

stats_router = APIRouter()


@stats_router.get("/stats")
def get_stats():
    """Return platform stats: user counts, subscription status breakdown, most active user, avg messages per session."""
    try:
        total_users = user_profile.count_documents({})
        total_paid = user_profile.count_documents({"is_paid": True})
        total_unpaid = total_users - total_paid

        # Link generated but payment never completed
        link_generated_not_paid = user_profile.count_documents({
            "early_bird_sub_id": {"$exists": True},
            "is_paid": False,
        })

        # Subscription status breakdown
        sub_status_pipeline = [
            {"$group": {
                "_id": {"$ifNull": ["$subscription_status", "no_subscription"]},
                "count": {"$sum": 1},
            }}
        ]
        sub_status_raw = list(user_profile.aggregate(sub_status_pipeline))
        subscription_status_breakdown = {
            doc["_id"]: doc["count"] for doc in sub_status_raw
        }

        # Total sessions and total messages across all sessions
        total_sessions = chat_sessions.count_documents({})
        session_stats_pipeline = [
            {"$project": {
                "email": 1,
                "msg_count": {"$size": {"$ifNull": ["$messages", []]}},
            }},
            {"$group": {
                "_id": None,
                "total_messages": {"$sum": "$msg_count"},
                "avg_messages_per_session": {"$avg": "$msg_count"},
            }}
        ]
        session_stats_result = list(chat_sessions.aggregate(session_stats_pipeline))
        session_stats = session_stats_result[0] if session_stats_result else {}
        total_messages = session_stats.get("total_messages", 0)
        avg_messages_per_session = round(session_stats.get("avg_messages_per_session", 0), 2)

        # Most active user by total messages sent across all their sessions
        most_active_pipeline = [
            {"$project": {
                "email": 1,
                "msg_count": {"$size": {"$ifNull": ["$messages", []]}},
            }},
            {"$group": {
                "_id": "$email",
                "total_messages": {"$sum": "$msg_count"},
                "session_count": {"$sum": 1},
            }},
            {"$sort": {"total_messages": -1}},
            {"$limit": 1},
        ]
        most_active_result = list(chat_sessions.aggregate(most_active_pipeline))
        most_active_user = None
        if most_active_result:
            top = most_active_result[0]
            user_doc = user_profile.find_one({"email": top["_id"]}, {"_id": 0, "username": 1})
            most_active_user = {
                "email": top["_id"],
                "username": user_doc.get("username", "") if user_doc else "",
                "total_messages": top["total_messages"],
                "session_count": top["session_count"],
            }

        return {
            "total_users": total_users,
            "total_paid": total_paid,
            "total_unpaid": total_unpaid,
            "link_generated_not_paid": link_generated_not_paid,
            "subscription_status_breakdown": subscription_status_breakdown,
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "avg_messages_per_session": avg_messages_per_session,
            "most_active_user": most_active_user,
        }

    except Exception as e:
        logger.error("System: error fetching stats", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)
