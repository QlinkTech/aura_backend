from elevenlabs.client import ElevenLabs
from app.utils.env_load import elevenlabs_api_key
from app.utils.logger_config import logger

_client = ElevenLabs(api_key=elevenlabs_api_key)


def transcribe_audio(file_path: str) -> str:
    logger.info("Transcribing audio via ElevenLabs STT")
    try:
        with open(file_path, "rb") as f:
            result = _client.speech_to_text.convert(
                file=f,
                model_id="scribe_v2",
                language_code="eng",
            )
        transcript = result.text
        logger.info("ElevenLabs STT transcription successful")
        return transcript
    except FileNotFoundError:
        logger.error("Audio file not found for transcription")
        raise
    except Exception as e:
        logger.error("ElevenLabs STT transcription failed", extra={"error": str(e)})
        raise
