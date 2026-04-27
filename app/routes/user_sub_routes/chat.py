from fastapi import APIRouter, Depends, HTTPException
from app.utils.schema import ChatModel
from app.services.auth_service import get_active_user
from app.services.db.mongo_utils import user_profile
from app.services.db.chat_session_utils import (
    create_chat_session,
    list_chat_sessions,
    get_session_messages,
    delete_chat_session,
)
from app.core.agent import chat_agent, generate_ice_breakers
from app.utils.logger_config import logger

chat_router = APIRouter()


@chat_router.post("/chat")
def chat(data: ChatModel, current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("Chat request received", extra={"email": email, "session_id": data.session_id})
    user = user_profile.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=403, detail="No user found")
    result = chat_agent(
        email=email,
        message=data.message,
        session_id=data.session_id,
        username=user.get("username", ""),
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {"reply": result["reply"], "session_id": result["session_id"]}


@chat_router.get("/chat/ice-breakers")
def ice_breakers(current_user=Depends(get_active_user)):
    """Return 4 personalised conversation-starter suggestions for the user."""
    email = current_user["email"]
    user = user_profile.find_one({"email": email}, {"username": 1})
    username = user.get("username", "") if user else ""
    result = generate_ice_breakers(email=email, username=username)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return {"starters": result["starters"]}


@chat_router.post("/chat/session")
def new_session(current_user=Depends(get_active_user)):
    """Create a fresh chat session and return its ID."""
    email = current_user["email"]
    session_id = create_chat_session(email)
    logger.info("New chat session created via route", extra={"email": email, "session_id": session_id})
    return {"session_id": session_id}


@chat_router.get("/chat/sessions")
def get_sessions(current_user=Depends(get_active_user)):
    """List all chat sessions for the user, newest first."""
    email = current_user["email"]
    sessions = list_chat_sessions(email)
    return {"sessions": sessions}


@chat_router.get("/chat/session/{session_id}")
def get_session(session_id: str, current_user=Depends(get_active_user)):
    """Return all messages in a session."""
    email = current_user["email"]
    messages = get_session_messages(session_id=session_id, email=email, limit=200)
    if messages is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "messages": messages}


@chat_router.delete("/chat/session/{session_id}")
def remove_session(session_id: str, current_user=Depends(get_active_user)):
    """Delete a chat session."""
    email = current_user["email"]
    deleted = delete_chat_session(session_id=session_id, email=email)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted"}
