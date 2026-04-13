from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.services.db.mongo_utils import user_profile
from app.utils.logger_config import logger

stats_router = APIRouter()

# Users with a subscription link generated but never completed payment:
# they have early_bird_sub_id set but is_paid is False
# subscription_status breakdown covers all states from Razorpay webhooks


@stats_router.get("/stats")
def get_stats():
    """Return platform stats: user counts, subscription status breakdown, most active user, avg chat length."""
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

        # Most active user by chat history length
        most_active_pipeline = [
            {"$project": {
                "_id": 0,
                "email": 1,
                "username": 1,
                "chat_count": {"$size": {"$ifNull": ["$chat_history", []]}},
                "last_active": "$updated_at",
            }},
            {"$sort": {"chat_count": -1}},
            {"$limit": 1},
        ]
        most_active_result = list(user_profile.aggregate(most_active_pipeline))
        most_active_user = most_active_result[0] if most_active_result else None

        # Average chat history length across all users
        avg_pipeline = [
            {"$project": {
                "chat_len": {"$size": {"$ifNull": ["$chat_history", []]}}
            }},
            {"$group": {
                "_id": None,
                "avg_chat_length": {"$avg": "$chat_len"}
            }}
        ]
        avg_result = list(user_profile.aggregate(avg_pipeline))
        avg_chat_length = round(avg_result[0]["avg_chat_length"], 2) if avg_result else 0

        return {
            "total_users": total_users,
            "total_paid": total_paid,
            "total_unpaid": total_unpaid,
            "link_generated_not_paid": link_generated_not_paid,
            "subscription_status_breakdown": subscription_status_breakdown,
            "most_active_user": most_active_user,
            "avg_chat_length": avg_chat_length,
        }

    except Exception as e:
        logger.error("System: error fetching stats", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)
