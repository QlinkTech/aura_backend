from fastapi import APIRouter, Depends, HTTPException
from app.utils.schema import ChatModel
from app.services.auth_service import get_active_user
from app.services.db.mongo_utils import user_profile
from app.services.db.user_profile_utils import get_chat_history
from app.core.agent import chat_agent
from app.utils.logger_config import logger

chat_router = APIRouter()


@chat_router.post("/chat")
def chat(data: ChatModel, current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("Chat request received", extra={"email": email})
    user = user_profile.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=403, detail="No user found")
    result = chat_agent(email=email, message=data.message, username=user.get("username", ""))
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {"reply": result["reply"]}


@chat_router.get("/chat-history")
def chat_history(current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("Chat history request", extra={"email": email})
    return get_chat_history(email=email)
