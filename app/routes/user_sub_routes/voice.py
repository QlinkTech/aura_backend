import asyncio
import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from app.services.auth_service import get_active_user
from app.services.voice_service.sarvam_utils import transcribe_audio
from app.utils.logger_config import logger

voice_router = APIRouter()

ALLOWED_AUDIO_TYPES = {"audio/wav", "audio/mpeg", "audio/mp4", "audio/webm", "audio/ogg", "audio/x-m4a"}
MAX_AUDIO_SIZE_MB = 10
CHUNK_SIZE = 1024 * 1024  # 1 MB


@voice_router.post("/voice-to-text")
async def voice_to_text(audio: UploadFile = File(...), current_user=Depends(get_active_user)):
    logger.info("Voice to text request")

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
