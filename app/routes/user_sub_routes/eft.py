from fastapi import APIRouter, Depends, HTTPException
from app.utils.schema import EFTChatModel
from app.services.auth_service import get_active_user
from app.core.eft_agent.eft_agent import eft_chat
from app.services.db.eft_utils import list_eft_sessions, get_eft_session, delete_eft_session
from app.utils.logger_config import logger

eft_router = APIRouter()


@eft_router.post("/eft/chat")
def eft_chat_endpoint(data: EFTChatModel, current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("EFT chat request", extra={"email": email, "session_id": data.session_id})

    result = eft_chat(email=email, message=data.message, session_id=data.session_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("message", "EFT session error"))

    return {
        "session_id": result["session_id"],
        "reply": result["reply"],
        "is_complete": result["is_complete"],
        "audio_url": result["audio_url"],
    }


@eft_router.get("/eft/sessions")
def list_sessions(current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("EFT list sessions", extra={"email": email})
    sessions = list_eft_sessions(email=email)
    return {"sessions": sessions}


@eft_router.get("/eft/sessions/{session_id}")
def get_session(session_id: str, current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("EFT get session", extra={"email": email, "session_id": session_id})
    session = get_eft_session(session_id=session_id, email=email)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@eft_router.delete("/eft/sessions/{session_id}")
def remove_session(session_id: str, current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("EFT delete session", extra={"email": email, "session_id": session_id})
    deleted = delete_eft_session(session_id=session_id, email=email)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True}
