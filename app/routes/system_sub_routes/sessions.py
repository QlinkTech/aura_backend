from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from typing import Optional
from app.services.db.mongo_utils import eft_sessions, guided_viz_sessions, user_profile
from app.utils.logger_config import logger

system_sessions_router = APIRouter()


def _username(email: str) -> str:
    doc = user_profile.find_one({"email": email}, {"_id": 0, "username": 1})
    return doc.get("username", "") if doc else ""


# ── EFT Tapping ──────────────────────────────────────────────────────────────

@system_sessions_router.get("/eft/sessions")
def list_eft_sessions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    email: Optional[str] = Query(None),
    is_complete: Optional[bool] = Query(None),
):
    try:
        query = {}
        if email:
            query["email"] = email.lower()
        if is_complete is not None:
            query["is_complete"] = is_complete

        skip  = (page - 1) * limit
        total = eft_sessions.count_documents(query)

        cursor = (
            eft_sessions.find(query, {"_id": 0, "messages": 1, "session_id": 1,
                                      "email": 1, "is_complete": 1, "audio_url": 1,
                                      "created_at": 1, "updated_at": 1})
            .sort("updated_at", -1)
            .skip(skip)
            .limit(limit)
        )

        sessions = []
        for doc in cursor:
            messages = doc.pop("messages", [])
            sessions.append({
                **doc,
                "total_messages":  len(messages),
                "user_messages":   sum(1 for m in messages if m.get("role") == "user"),
            })

        agg = list(eft_sessions.aggregate([
            {"$match": query},
            {"$group": {
                "_id": None,
                "completed": {"$sum": {"$cond": ["$is_complete", 1, 0]}},
            }}
        ]))
        agg = agg[0] if agg else {}

        return {
            "summary": {
                "total_sessions":     total,
                "completed_sessions": agg.get("completed", 0),
                "pending_sessions":   total - agg.get("completed", 0),
            },
            "sessions": sessions,
            "page":  page,
            "limit": limit,
            "pages": (total + limit - 1) // limit,
        }

    except Exception as e:
        logger.error("System: error listing EFT sessions", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@system_sessions_router.get("/eft/sessions/{session_id}")
def get_eft_session(session_id: str):
    try:
        doc = eft_sessions.find_one({"session_id": session_id}, {"_id": 0})
        if not doc:
            return JSONResponse({"error": "Session not found"}, status_code=404)

        messages  = doc.get("messages", [])
        msg_count = len(messages)
        user_turns = sum(1 for m in messages if m.get("role") == "user")

        return {
            "session_id":  doc["session_id"],
            "email":       doc.get("email"),
            "username":    _username(doc.get("email", "")),
            "is_complete": doc.get("is_complete"),
            "audio_url":   doc.get("audio_url"),
            "created_at":  doc.get("created_at"),
            "updated_at":  doc.get("updated_at"),
            "stats": {
                "total_messages":  msg_count,
                "user_messages":   user_turns,
                "sanaya_messages": msg_count - user_turns,
            },
            "messages": messages,
        }

    except Exception as e:
        logger.error("System: error fetching EFT session", extra={"session_id": session_id, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Guided Visualization ──────────────────────────────────────────────────────

@system_sessions_router.get("/guided-viz/sessions")
def list_guided_viz_sessions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    email: Optional[str] = Query(None),
    is_complete: Optional[bool] = Query(None),
):
    try:
        query = {}
        if email:
            query["email"] = email.lower()
        if is_complete is not None:
            query["is_complete"] = is_complete

        skip  = (page - 1) * limit
        total = guided_viz_sessions.count_documents(query)

        cursor = (
            guided_viz_sessions.find(
                query,
                {"_id": 0, "r2_key": 0, "script": 0}
            )
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )

        agg = list(guided_viz_sessions.aggregate([
            {"$match": query},
            {"$group": {
                "_id": None,
                "completed": {"$sum": {"$cond": ["$is_complete", 1, 0]}},
                "errored":   {"$sum": {"$cond": [{"$eq": ["$error", True]}, 1, 0]}},
            }}
        ]))
        agg = agg[0] if agg else {}
        completed = agg.get("completed", 0)
        errored   = agg.get("errored", 0)

        return {
            "summary": {
                "total_sessions":     total,
                "completed_sessions": completed,
                "errored_sessions":   errored,
                "pending_sessions":   total - completed - errored,
            },
            "sessions": [doc for doc in cursor],
            "page":  page,
            "limit": limit,
            "pages": (total + limit - 1) // limit,
        }

    except Exception as e:
        logger.error("System: error listing guided viz sessions", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@system_sessions_router.get("/guided-viz/sessions/{session_id}")
def get_guided_viz_session(session_id: str):
    try:
        doc = guided_viz_sessions.find_one({"session_id": session_id}, {"_id": 0})
        if not doc:
            return JSONResponse({"error": "Session not found"}, status_code=404)

        return {
            **doc,
            "username": _username(doc.get("email", "")),
        }

    except Exception as e:
        logger.error("System: error fetching guided viz session", extra={"session_id": session_id, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)
