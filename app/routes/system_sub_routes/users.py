import re
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
    "is_paid": 1, "is_bypassed": 1, "early_bird_plan_key": 1, "early_bird_sub_id": 1,
    "subscription_status": 1, "trial_end_at": 1, "paid_until": 1, "created_at": 1, "updated_at": 1,
    "engagement_tier": 1, "trial_engagement_tier": 1, "engagement_status": 1,
}

_ACTIVE_PAYMENT_STATUSES = {"active", "authenticated", "charged"}
# Mirrors _LAPSED_SUBSCRIPTION_STATUSES in auth_service.py / access_sync.py — statuses that mean
# "won't renew" but don't necessarily end access immediately if a paid-up period is still running.
# Used for revocation-eligibility checks (does this user's access need re-checking at all).
_LAPSED_PAYMENT_STATUSES = {"cancelled", "paused", "free", "expired", "halted"}
# Narrower than the above, for display only: a REAL subscription that lapsed. Excludes "free" —
# activate_free_plan() sets subscription_status="free" with no early_bird_sub_id/plan_key at all,
# so a "free" user still inside their window is on a free trial, not a cancelled subscription.
_CANCELLED_SUBSCRIPTION_STATUSES = {"cancelled", "paused", "expired", "halted"}


def _access_expires_at(doc: dict) -> int:
    """Timestamp this user's current access actually runs out at, if any.

    paid_until (cancel-at-cycle-end paid access) takes precedence over trial_end_at
    (free trial window) when both are set — same precedence used to decide real
    access in auth_service.revoke_access_if_lapsed / access_sync._compute_is_paid.
    """
    return doc.get("paid_until") or doc.get("trial_end_at") or 0


def _resolve_payment_status(doc: dict) -> str:
    if doc.get("is_bypassed"):
        return "granted_access"

    is_paid = doc.get("is_paid", False)
    sub_status = doc.get("subscription_status")
    has_sub = bool(doc.get("early_bird_sub_id"))

    if is_paid:
        if sub_status in _ACTIVE_PAYMENT_STATUSES:
            return "active"
        if sub_status in _CANCELLED_SUBSCRIPTION_STATUSES:
            # A real paying customer who cancelled (or was paused/halted) but is still inside
            # their paid-up window — distinct from someone who never converted. Previously
            # mislabeled "trial_active", which reads as "still on a free trial".
            expires_at = _access_expires_at(doc)
            if expires_at and int(time.time()) < expires_at:
                return "cancelled_active"
        return "free_trail"
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
    is_bypassed: Optional[bool] = Query(None, description="Filter by granted access (bypass) status"),
    search: Optional[str] = Query(None, description="Search by email, username, or phone"),
    engagement_status: Optional[str] = Query(None, description="Filter by engagement status: cold, warm, hot, converted, no_trial"),
    payment_status: Optional[str] = Query(None, description="Filter by resolved payment status: granted_access, active, cancelled_active, free_trail, payment_pending, not_initiated (or a raw subscription_status value)"),
):
    """List all users with pagination, sorted by most recently active."""
    try:
        query: dict = {}

        if is_paid is not None:
            query["is_paid"] = is_paid

        if is_bypassed is True:
            query["is_bypassed"] = True
        elif is_bypassed is False:
            query["is_bypassed"] = {"$ne": True}

        if engagement_status is not None:
            query["engagement_status"] = engagement_status

        if search:
            search_pattern = re.escape(search)
            query["$or"] = [
                {"email": {"$regex": search_pattern, "$options": "i"}},
                {"username": {"$regex": search_pattern, "$options": "i"}},
                {"phone": {"$regex": search_pattern, "$options": "i"}},
            ]

        skip = (page - 1) * limit

        if payment_status is not None:
            # payment_status is derived (not a stored field), so it can't be matched in Mongo directly.
            # Resolve it per-doc against the full filtered set, then paginate in Python.
            matched_docs = [
                doc for doc in user_profile.find(query, LIST_FIELDS).sort("updated_at", -1)
                if _resolve_payment_status(doc) == payment_status
            ]
            total = len(matched_docs)
            page_docs = matched_docs[skip: skip + limit]
        else:
            total = user_profile.count_documents(query)
            page_docs = list(
                user_profile.find(query, LIST_FIELDS)
                .sort("updated_at", -1)
                .skip(skip)
                .limit(limit)
            )

        users = []
        for doc in page_docs:
            users.append({
                "email": doc.get("email", ""),
                "username": doc.get("username", ""),
                "phone": doc.get("phone", ""),
                "is_paid": doc.get("is_paid", False),
                "payment_status": _resolve_payment_status(doc),
                "plan": doc.get("early_bird_plan_key") if doc.get("is_paid") else ("bypassed" if doc.get("is_bypassed") else "free"),
                "is_bypassed": doc.get("is_bypassed", False),
                "trial_end_at": doc.get("trial_end_at"),
                "access_until": _access_expires_at(doc) or None,
                "last_active": doc.get("updated_at"),
                "created_at": doc.get("created_at"),
                "engagement_tier": doc.get("engagement_tier"),
                "trial_engagement_tier": doc.get("trial_engagement_tier"),
                "engagement_status": doc.get("engagement_status"),
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

        user["payment_status"] = _resolve_payment_status(user)
        user["access_until"] = _access_expires_at(user) or None

        return user

    except Exception as e:
        logger.error("System: error fetching user", extra={"email": email, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@users_router.post("/users/{email}/bypass-payment")
def bypass_user_payment(email: str):
    """Toggle bypass access for a user. Not applicable if the user already has a real paid subscription."""
    try:
        email = email.lower()
        user = user_profile.find_one({"email": email}, {"_id": 1, "is_paid": 1, "is_bypassed": 1, "subscription_status": 1, "trial_end_at": 1, "paid_until": 1})
        if not user:
            return JSONResponse({"error": "User not found"}, status_code=404)

        if user.get("is_paid") and user.get("subscription_status") in _LAPSED_PAYMENT_STATUSES:
            if int(time.time()) >= _access_expires_at(user):
                user_profile.update_one({"email": email}, {"$set": {"is_paid": False, "updated_at": int(time.time())}})
                user["is_paid"] = False

        if user.get("is_paid"):
            return JSONResponse(
                {"error": "User already has an active paid subscription — bypass is not applicable."},
                status_code=400,
            )

        new_bypassed = not user.get("is_bypassed", False)
        user_profile.update_one(
            {"email": email},
            {"$set": {"is_bypassed": new_bypassed, "updated_at": int(time.time())}},
        )

        logger.info("System: bypass toggled", extra={"email": email, "is_bypassed": new_bypassed})
        return {"success": True, "is_bypassed": new_bypassed}

    except Exception as e:
        logger.error("System: error toggling bypass", extra={"email": email, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)
