import io
import json
import uuid

from openai import OpenAI
from elevenlabs.client import ElevenLabs

from app.core.eft_agent.eft_agent_utils import EFT_SYSTEM_PROMPT, EFT_TOOLS
from app.services.db.eft_utils import (
    create_eft_session,
    get_eft_session,
    add_session_message,
    get_session_messages,
    mark_session_complete,
)
from app.services.storage.r2_utils import upload_media
from app.utils.env_load import openai_api_key, elevenlabs_api_key
from app.utils.logger_config import logger
from app.services import event_bus

openai_client = OpenAI(api_key=openai_api_key)
elevenlabs_client = ElevenLabs(api_key=elevenlabs_api_key)

# aura — calm, warm voice well suited for guided tapping sessions
EFT_VOICE_ID = "hnMOqbQV1aV5iom08kJd"

MAX_TOOL_ITERATIONS = 3


def _generate_and_store_audio(email: str, session_id: str, script: str) -> str:
    """Convert script to speech via ElevenLabs and upload to R2. Returns public URL."""
    logger.info("Generating EFT audio via ElevenLabs", extra={"email": email, "session_id": session_id})

    audio_chunks = elevenlabs_client.text_to_speech.convert(
        voice_id=EFT_VOICE_ID,
        text=script,
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
    )

    audio_bytes = b"".join(audio_chunks)
    key = f"eft_audio/{email}/{session_id}.mp3"
    url = upload_media(io.BytesIO(audio_bytes), key, content_type="audio/mpeg")

    logger.info("EFT audio stored in R2", extra={"email": email, "session_id": session_id, "url": url})
    return url


def eft_chat(email: str, message: str, session_id: str = None) -> dict:
    email = email.lower()
    logger.info("EFT chat invoked", extra={"email": email, "session_id": session_id})

    try:
        if not session_id:
            session_id = create_eft_session(email)
            logger.info("New EFT session created", extra={"email": email, "session_id": session_id})
        else:
            session = get_eft_session(session_id=session_id, email=email)
            if not session:
                return {"success": False, "message": "Session not found."}
            if session.get("is_complete"):
                return {
                    "success": True,
                    "session_id": session_id,
                    "reply": "This session has already been completed. Start a new one when you're ready.",
                    "is_complete": True,
                    "audio_url": session.get("audio_url"),
                }

        history = get_session_messages(session_id=session_id, email=email)

        messages = [
            {"role": "system", "content": EFT_SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": message},
        ]

        reply = None
        audio_url = None
        is_complete = False

        for iteration in range(MAX_TOOL_ITERATIONS):
            response = openai_client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages,
                tools=EFT_TOOLS,
                tool_choice="auto",
                temperature=1.0,
            )

            result = response.choices[0]

            if result.finish_reason != "tool_calls":
                reply = result.message.content
                break

            tool_call = result.message.tool_calls[0]
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments)

            logger.info("EFT tool call", extra={"email": email, "tool": func_name, "iteration": iteration})

            if func_name == "generate_eft_audio":
                script = func_args.get("script", "")
                try:
                    audio_url = _generate_and_store_audio(email, session_id, script)
                    mark_session_complete(session_id=session_id, audio_url=audio_url)
                    is_complete = True
                    event_bus.publish(email, {
                        "type": "eft_complete",
                        "title": "Your tapping session is ready",
                        "body": "Tap to listen.",
                        "data": {"session_id": session_id, "audio_url": audio_url},
                    })
                    tool_result_content = json.dumps({"audio_url": audio_url, "success": True})
                except Exception as audio_err:
                    logger.error("EFT audio generation failed", extra={"email": email, "error": str(audio_err)})
                    tool_result_content = json.dumps({"success": False, "error": str(audio_err)})
            else:
                logger.warning("Unknown EFT tool called", extra={"email": email, "tool": func_name})
                break

            messages.append({
                "role": "assistant",
                "tool_calls": [{
                    "id": tool_call.id,
                    "type": "function",
                    "function": {"name": func_name, "arguments": json.dumps(func_args)},
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result_content,
            })

        if not reply:
            logger.warning("EFT agent loop exhausted without reply", extra={"email": email})
            reply = "I'm right here with you. Take a breath. What are you noticing?"

        add_session_message(session_id=session_id, role="user", content=message)
        add_session_message(session_id=session_id, role="assistant", content=reply)

        logger.info("EFT reply generated", extra={"email": email, "session_id": session_id, "is_complete": is_complete})

        return {
            "success": True,
            "session_id": session_id,
            "reply": reply,
            "is_complete": is_complete,
            "audio_url": audio_url,
        }

    except Exception as e:
        logger.error("[eft_chat] Error", extra={"email": email, "error": str(e)})
        return {"success": False, "message": "Something went wrong. Please try again."}
