from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from app.utils.schema import ChatModel, ReGenerateVisionModel
from app.services.auth_service import get_current_user
from app.utils.db.mongo_utils import user_profile, get_chat_history, update_vision_board, get_user_details
from app.core.agent import chat_agent
from app.core.vision_board.genrate_vision_board import generate_vision_background
from app.utils.logger_config import logger

user_router = APIRouter()

@user_router.get("/vision-board/{email}")
def get_vision_board(email: str, current_user=Depends(get_current_user)):
    email = email.lower()
    logger.info("Get vision board request", extra={"email": email})
    if current_user["email"] != email:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = user_profile.find_one({"email": email})
    if not user or "vision_board_url" not in user:
        raise HTTPException(status_code=404, detail="Vision board not found")
    return {"vision_board_url": user["vision_board_url"]}

@user_router.post("/chat")
def chat(data: ChatModel, current_user=Depends(get_current_user)):
    logger.info("Chat request received", extra={"email": data.email})
    if current_user["email"] != data.email.lower():
        raise HTTPException(status_code=403, detail="Forbidden")
    user = user_profile.find_one({"email": data.email.lower()})
    if not user:
        raise HTTPException(status_code=403, detail="No user found")

    result = chat_agent(email=data.email.lower(), message=data.message)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {"reply": result["reply"]}

@user_router.get("/chat_history/{email}")
def chat_history(email: str, current_user=Depends(get_current_user)):
    email = email.lower()
    logger.info("Chat history request", extra={"email": email})
    if current_user["email"] != email:
        raise HTTPException(status_code=403, detail="Forbidden")
    return get_chat_history(email=email)

@user_router.post("/regenerate-vision")
def generate_vision(data: ReGenerateVisionModel, background_tasks: BackgroundTasks, current_user=Depends(get_current_user)):
    logger.info("Regenerate vision board request", extra={"email": data.email, "vibe": data.vibe})
    email = data.email.lower()

    if current_user["email"] != email:
        raise HTTPException(status_code=403, detail="Forbidden")
    update_vision_board(email, "preparing")
    try:
        background_tasks.add_task(generate_vision_background, email, data.answers, data.vibe)

        return {"sucess": True, "token_type": "bearer"}
    except Exception as e:
        raise e

@user_router.get("/user-profile")
def get_user(email: str, current_user=Depends(get_current_user)):
    email = email.lower()
    logger.info("Get user profile request", extra={"email": email})
    return get_user_details(email=email)
