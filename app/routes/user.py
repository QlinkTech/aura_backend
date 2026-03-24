import asyncio
import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from app.utils.schema import ChatModel, ReGenerateVisionModel, GenerateVisionRequest
from app.services.voice_service.sarvam_utils import transcribe_audio
from app.services.auth_service import get_active_user
from app.services.db.mongo_utils import user_profile
from app.services.db.user_profile_utils import get_chat_history, update_vision_board, get_user_details
from app.core.agent import chat_agent
from app.core.vision_board.genrate_vision_board import generate_vision_background
from app.utils.logger_config import logger

user_router = APIRouter()

@user_router.get("/vision-board/{email}")
def get_vision_board(email: str, current_user=Depends(get_active_user)):
    email = email.lower()
    logger.info("Get vision board request", extra={"email": email})
    if current_user["email"] != email:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = user_profile.find_one({"email": email})
    if not user or "vision_board_url" not in user:
        raise HTTPException(status_code=404, detail="Vision board not found")
    return {"vision_board_url": user["vision_board_url"]}

@user_router.post("/chat")
def chat(data: ChatModel, current_user=Depends(get_active_user)):
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
def chat_history(email: str, current_user=Depends(get_active_user)):
    email = email.lower()
    logger.info("Chat history request", extra={"email": email})
    if current_user["email"] != email:
        raise HTTPException(status_code=403, detail="Forbidden")
    return get_chat_history(email=email)

@user_router.post("/generate-vision")
def generate_vision(data: GenerateVisionRequest, background_tasks: BackgroundTasks, current_user=Depends(get_active_user)):
    email = current_user["email"]
    logger.info("Generate vision board request", extra={"email": email})
    update_vision_board(email, "preparing")
    background_tasks.add_task(generate_vision_background, email, data.answers, data.vibe)
    logger.info("Vision board generation queued", extra={"email": email})
    return {"success": True}

@user_router.post("/regenerate-vision")
def generate_vision(data: ReGenerateVisionModel, background_tasks: BackgroundTasks, current_user=Depends(get_active_user)):
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
def get_user(email: str, current_user=Depends(get_active_user)):
    email = email.lower()
    logger.info("Get user profile request", extra={"email": email})
    return get_user_details(email=email)

ALLOWED_AUDIO_TYPES = {"audio/wav", "audio/mpeg", "audio/mp4", "audio/webm", "audio/ogg", "audio/x-m4a"}
MAX_AUDIO_SIZE_MB = 10
CHUNK_SIZE = 1024 * 1024  # 1 MB

@user_router.post("/voice-to-text")
async def voice_to_text(audio: UploadFile = File(...), current_user=Depends(get_active_user)):
    logger.info("Voice to text request", extra={"email": current_user["email"], "filename": audio.filename, "content_type": audio.content_type})

    if audio.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {audio.content_type}")

    suffix = os.path.splitext(audio.filename)[-1] or ".wav"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            total_bytes = 0
            while chunk := await audio.read(CHUNK_SIZE):
                total_bytes += len(chunk)
                if total_bytes > MAX_AUDIO_SIZE_MB * 1024 * 1024:
                    raise HTTPException(status_code=413, detail=f"Audio file exceeds {MAX_AUDIO_SIZE_MB}MB limit")
                tmp.write(chunk)

        transcript = await asyncio.to_thread(transcribe_audio, tmp_path)
        return {"transcript": transcript}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Voice to text failed", extra={"email": current_user["email"], "error": str(e)})
        raise HTTPException(status_code=500, detail="Transcription failed")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
