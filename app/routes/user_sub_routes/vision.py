from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from app.utils.schema import GenerateVisionRequest, ReGenerateVisionModel
from app.services.auth_service import get_active_user
from app.services.db.mongo_utils import user_profile
from app.services.db.user_profile_utils import update_vision_board
from app.core.vision_board.genrate_vision_board import generate_vision_background
from app.utils.logger_config import logger

vision_router = APIRouter()


@vision_router.get("/vision-board/{email}")
def get_vision_board(email: str, current_user=Depends(get_active_user)):
    email = email.lower()
    logger.info("Get vision board request", extra={"email": email})
    if current_user["email"] != email:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = user_profile.find_one({"email": email})
    if not user or "vision_board_url" not in user:
        raise HTTPException(status_code=404, detail="Vision board not found")
    return {"vision_board_url": user["vision_board_url"]}


@vision_router.post("/generate-vision")
def generate_vision(data: GenerateVisionRequest, background_tasks: BackgroundTasks, current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("Generate vision board request", extra={"email": email})
    update_vision_board(email, "preparing")
    background_tasks.add_task(generate_vision_background, email, data.answers, data.vibe)
    logger.info("Vision board generation queued", extra={"email": email})
    return {"success": True}


@vision_router.post("/regenerate-vision")
def regenerate_vision(data: ReGenerateVisionModel, background_tasks: BackgroundTasks, current_user=Depends(get_active_user)):
    email = data.email.lower()
    logger.info("Regenerate vision board request", extra={"email": email, "vibe": data.vibe})
    if current_user["email"] != email:
        raise HTTPException(status_code=403, detail="Forbidden")
    update_vision_board(email, "preparing")
    background_tasks.add_task(generate_vision_background, email, data.answers, data.vibe)
    return {"success": True}
