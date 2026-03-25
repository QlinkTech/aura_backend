from app.services.voice_service.servam_client import sarvam_client
from app.utils.logger_config import logger


def transcribe_audio(file_path: str) -> str:
    logger.info("Transcribing audio file")
    try:
        with open(file_path, "rb") as f:
            response = sarvam_client.speech_to_text.transcribe(
                file=f,
                model="saaras:v3",
                mode="transcribe",
            )
        logger.info("Transcription successful")
        return response.transcript
    except FileNotFoundError:
        logger.error("Audio file not found")
        raise
    except Exception as e:
        logger.error("Transcription failed")
        raise
