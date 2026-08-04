import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from app.utils.schema import GuidedVizModel
from app.services.auth_service import get_active_user
from app.services.db.mongo_utils import user_profile
from app.core.guided_viz_agent.guided_viz_agent import generate_guided_viz
from app.services.db.guided_viz_utils import create_guided_viz_session, list_guided_viz_sessions, get_guided_viz_session, delete_guided_viz_session
from app.utils.logger_config import logger

guided_viz_router = APIRouter()


@guided_viz_router.post("/guided-viz/generate")
def guided_viz_generate(data: GuidedVizModel, background_tasks: BackgroundTasks, current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("Guided viz generate request", extra={"email": email})

    user = user_profile.find_one({"email": email}, {"username": 1})
    username = user.get("username", "") if user else ""

    session_id = str(uuid.uuid4())
    create_guided_viz_session(email=email, session_id=session_id, user_message=data.message)

    background_tasks.add_task(generate_guided_viz, email=email, message=data.message, session_id=session_id, username=username)

    return {
        "session_id": session_id,
        "status": "in_progress",
        "message": "Your visualization is being prepared. You'll receive a notification when it's ready.",
    }


@guided_viz_router.get("/guided-viz/sessions")
def list_sessions(current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("Guided viz list sessions", extra={"email": email})
    sessions = list_guided_viz_sessions(email=email)
    return {"sessions": sessions}


@guided_viz_router.get("/guided-viz/sessions/{session_id}")
def get_session(session_id: str, current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("Guided viz get session", extra={"email": email, "session_id": session_id})
    session = get_guided_viz_session(session_id=session_id, email=email)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@guided_viz_router.delete("/guided-viz/sessions/{session_id}")
def remove_session(session_id: str, current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("Guided viz delete session", extra={"email": email, "session_id": session_id})
    deleted = delete_guided_viz_session(session_id=session_id, email=email)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True}
