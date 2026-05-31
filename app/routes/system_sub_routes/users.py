import time
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from typing import Optional
from app.services.db.mongo_utils import user_profile, chat_sessions
from app.utils.logger_config import logger

users_router = APIRouter()

EXCLUDED_FIELDS = {"password": 0}
LIST_FIELDS = {
    "_id": 0, "email": 1, "username": 1, "phone": 1,
    "is_paid": 1, "early_bird_plan_key": 1, "early_bird_sub_id": 1,
    "subscription_status": 1, "trial_end_at": 1, "created_at": 1, "updated_at": 1,
}

_ACTIVE_PAYMENT_STATUSES = {"active", "authenticated", "charged"}

def _resolve_payment_status(doc: dict) -> str:
    is_paid = doc.get("is_paid", False)
    sub_status = doc.get("subscription_status")
    has_sub = bool(doc.get("early_bird_sub_id"))

    if is_paid:
        if sub_status == "cancelled":
            trial_end_at = doc.get("trial_end_at", 0)
            if trial_end_at and int(time.time()) < trial_end_at:
                return "trial_active"
        return "active" if sub_status in _ACTIVE_PAYMENT_STATUSES else "granted_access"
    if sub_status:
        return sub_status
    if has_sub:
        return "payment_pending"
    return "not_initiated"


@users_router.get("/users")
def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    is_paid: Optional[bool] = Query(None),
    search: Optional[str] = Query(None, description="Search by email or username"),
):
    """List all users with pagination, sorted by most recently active."""
    try:
        query: dict = {}

        if is_paid is not None:
            query["is_paid"] = is_paid

        if search:
            query["$or"] = [
                {"email": {"$regex": search, "$options": "i"}},
                {"username": {"$regex": search, "$options": "i"}},
            ]

        skip = (page - 1) * limit
        total = user_profile.count_documents(query)

        cursor = (
            user_profile.find(query, LIST_FIELDS)
            .sort("updated_at", -1)
            .skip(skip)
            .limit(limit)
        )

        users = []
        for doc in cursor:
            users.append({
                "email": doc.get("email", ""),
                "username": doc.get("username", ""),
                "phone": doc.get("phone", ""),
                "is_paid": doc.get("is_paid", False),
                "payment_status": _resolve_payment_status(doc),
                "plan": doc.get("early_bird_plan_key") if doc.get("is_paid") else None,
                "trial_end_at": doc.get("trial_end_at"),
                "last_active": doc.get("updated_at"),
                "created_at": doc.get("created_at"),
            })

        return {
            "users": users,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit,
        }

    except Exception as e:
        logger.error("System: error listing users", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@users_router.get("/users/{email}")
def get_user(email: str):
    """Get full user details by email (password excluded), with chat session summary."""
    try:
        email = email.lower()
        user = user_profile.find_one({"email": email}, {**EXCLUDED_FIELDS, "_id": 0, "chat_history": 0})
        if not user:
            return JSONResponse({"error": "User not found"}, status_code=404)

        # Aggregate session stats for this user
        pipeline = [
            {"$match": {"email": email}},
            {"$project": {"msg_count": {"$size": {"$ifNull": ["$messages", []]}}}},
            {"$group": {"_id": None, "session_count": {"$sum": 1}, "total_messages": {"$sum": "$msg_count"}}},
        ]
        result = list(chat_sessions.aggregate(pipeline))
        user["chat_stats"] = result[0] if result else {"session_count": 0, "total_messages": 0}
        user["chat_stats"].pop("_id", None)

        return user

    except Exception as e:
        logger.error("System: error fetching user", extra={"email": email, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


ACTIVE_SUBSCRIPTION_STATUSES = {"active", "authenticated"}

@users_router.post("/users/{email}/bypass-payment")
def bypass_user_payment(email: str):
    """Toggle a user's paid status. Cannot revoke if they have an active subscription."""
    try:
        email = email.lower()
        user = user_profile.find_one({"email": email}, {"_id": 1, "is_paid": 1, "subscription_status": 1})
        if not user:
            return JSONResponse({"error": "User not found"}, status_code=404)

        current_status = user.get("is_paid", False)
        new_status = not current_status

        if not new_status and user.get("subscription_status") in ACTIVE_SUBSCRIPTION_STATUSES:
            return JSONResponse(
                {"error": "Cannot revoke payment — user has an active subscription. Cancel the subscription on Razorpay first."},
                status_code=400
            )

        user_profile.update_one(
            {"email": email},
            {"$set": {"is_paid": new_status, "updated_at": int(time.time())}}
        )

        logger.info("System: payment status toggled", extra={"email": email, "is_paid": new_status})
        return {"success": True, "is_paid": new_status}

    except Exception as e:
        logger.error("System: error toggling payment", extra={"email": email, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)
