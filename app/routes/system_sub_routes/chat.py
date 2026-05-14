from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from typing import Optional
from app.services.db.mongo_utils import chat_sessions, user_profile
from app.utils.logger_config import logger

system_chat_router = APIRouter()


@system_chat_router.get("/chat/sessions")
def list_all_sessions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    email: Optional[str] = Query(None, description="Filter by user email"),
):
    """List all chat sessions across all users with per-session message counts."""
    try:
        query = {}
        if email:
            query["email"] = email.lower()

        skip  = (page - 1) * limit
        total = chat_sessions.count_documents(query)

        cursor = (
            chat_sessions.find(
                query,
                {"_id": 0, "session_id": 1, "email": 1, "title": 1,
                 "created_at": 1, "updated_at": 1, "messages": 1}
            )
            .sort("updated_at", -1)
            .skip(skip)
            .limit(limit)
        )

        sessions = []
        for doc in cursor:
            messages    = doc.pop("messages", [])
            msg_count   = len(messages)
            user_turns  = sum(1 for m in messages if m.get("role") == "user")
            sessions.append({
                **doc,
                "total_messages":  msg_count,
                "user_messages":   user_turns,
                "sanaya_messages": msg_count - user_turns,
            })

        # Overall stats for this query scope
        agg = list(chat_sessions.aggregate([
            {"$match": query},
            {"$project": {"msg_count": {"$size": {"$ifNull": ["$messages", []]}}}},
            {"$group": {
                "_id": None,
                "total_messages":        {"$sum": "$msg_count"},
                "avg_messages_per_session": {"$avg": "$msg_count"},
            }}
        ]))
        agg = agg[0] if agg else {}

        return {
            "summary": {
                "total_sessions":           total,
                "total_messages":           agg.get("total_messages", 0),
                "avg_messages_per_session": round(agg.get("avg_messages_per_session", 0), 2),
            },
            "sessions": sessions,
            "page":  page,
            "limit": limit,
            "pages": (total + limit - 1) // limit,
        }

    except Exception as e:
        logger.error("System: error listing chat sessions", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@system_chat_router.get("/chat/sessions/{session_id}")
def get_session(session_id: str):
    """Return full message history for a session plus session-level stats."""
    try:
        doc = chat_sessions.find_one(
            {"session_id": session_id},
            {"_id": 0}
        )
        if not doc:
            return JSONResponse({"error": "Session not found"}, status_code=404)

        messages    = doc.get("messages", [])
        msg_count   = len(messages)
        user_turns  = sum(1 for m in messages if m.get("role") == "user")

        user_doc = user_profile.find_one(
            {"email": doc.get("email")}, {"_id": 0, "username": 1}
        )

        return {
            "session_id":  doc["session_id"],
            "email":       doc.get("email"),
            "username":    user_doc.get("username", "") if user_doc else "",
            "title":       doc.get("title", ""),
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
        logger.error("System: error fetching chat session", extra={"session_id": session_id, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)
