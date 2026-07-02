import io
import json
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI
from elevenlabs.client import ElevenLabs
from pydub import AudioSegment

from app.core.guided_viz_agent.guided_viz_agent_utils import (
    GUIDED_VIZ_SYSTEM_PROMPT,
    GUIDED_VIZ_TOOLS,
)
from app.services.db.guided_viz_utils import mark_session_complete, mark_session_error
from app.services.storage.r2_utils import upload_media
from app.utils.env_load import openai_api_key, elevenlabs_api_key
from app.utils.logger_config import logger
from app.core.agent import get_memory, get_journal_context
from app.services import event_bus

openai_client = OpenAI(api_key=openai_api_key)
elevenlabs_client = ElevenLabs(api_key=elevenlabs_api_key)

BREAK_TAG_RE = re.compile(r'<break\s+time="(\d+(?:\.\d+)?)s"\s*/>')
MAX_TOOL_ITERATIONS = 3
MUSIC_VOLUME_DB = -14
GUIDED_VIZ_VOICE_ID = "HJscYsobBBrJcoBI43WZ"

ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"

MUSIC_FILES = {
    "grounding": ASSETS_DIR / "Deep Theta Healing Meditation Music  174 Hz Solfeggio Frequency Royalty Free Music.mp3",
    "clarity":   ASSETS_DIR / "zenithhh-528hz-274962.mp3",
    "surrender": ASSETS_DIR / "nonenothingnowhere-174-hz-pain-release-156261.mp3",
}
MUSIC_FALLBACK = ASSETS_DIR / "universe_bella-financial-abundance-meditation-waves-233039.mp3"

# Pricing constants
_OPENAI_INPUT_PER_TOKEN  = 0.40 / 1_000_000   # USD per token  (gpt-4.1-mini input)
_OPENAI_OUTPUT_PER_TOKEN = 1.60 / 1_000_000   # USD per token  (gpt-4.1-mini output)
_ELEVENLABS_TTS_PER_CHAR = 0.18 / 1_000       # USD per char   (eleven_multilingual_v2)


def _parse_segments(script: str) -> list[tuple[str, object]]:
    segments = []
    last_end = 0
    for match in BREAK_TAG_RE.finditer(script):
        text = script[last_end:match.start()].strip()
        if text:
            segments.append(("text", text))
        duration_ms = int(float(match.group(1)) * 1000)
        segments.append(("pause", duration_ms))
        last_end = match.end()
    tail = script[last_end:].strip()
    if tail:
        segments.append(("text", tail))
    return segments


def _elevenlabs_tts(text: str) -> bytes:
    audio_chunks = elevenlabs_client.text_to_speech.convert(
        voice_id=GUIDED_VIZ_VOICE_ID,
        text=text,
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
    )
    return b"".join(audio_chunks)


def _build_voice_audio(script: str) -> tuple[bytes, int]:
    """Generate TTS per segment, insert silence for pauses. Returns (MP3 bytes, char_count)."""
    segments = _parse_segments(script)
    text_segments = [(i, seg) for i, (t, seg) in enumerate(segments) if t == "text"]
    tts_char_count = sum(len(text) for _, text in text_segments)

    tts_results: dict[int, bytes] = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_elevenlabs_tts, text): idx for idx, text in text_segments}
        for future in as_completed(futures):
            tts_results[futures[future]] = future.result()

    combined = AudioSegment.empty()
    for i, (seg_type, content) in enumerate(segments):
        if seg_type == "text":
            combined += AudioSegment.from_mp3(io.BytesIO(tts_results[i]))
        else:
            combined += AudioSegment.silent(duration=content)

    out = io.BytesIO()
    combined.export(out, format="mp3", bitrate="128k")
    return out.getvalue(), tts_char_count


def _load_music(music_mood: str) -> AudioSegment:
    path = MUSIC_FILES.get(music_mood, MUSIC_FALLBACK)
    if not path.exists():
        logger.warning("Music file not found, using fallback", extra={"path": str(path)})
        path = MUSIC_FALLBACK
    return AudioSegment.from_mp3(str(path))


def _mix_voice_and_music(voice_bytes: bytes, music_mood: str) -> bytes:
    voice = AudioSegment.from_mp3(io.BytesIO(voice_bytes))
    music = _load_music(music_mood) + MUSIC_VOLUME_DB

    total_ms = 3000 + len(voice) + 12000
    looped = AudioSegment.empty()
    while len(looped) < total_ms:
        looped += music
    looped = looped[:total_ms].fade_out(8000)

    mixed = looped.overlay(voice, position=3000)
    out = io.BytesIO()
    mixed.export(out, format="mp3", bitrate="128k")
    return out.getvalue()


def _generate_and_store_audio(
    email: str, session_id: str, script: str, music_mood: str
) -> tuple[str, int]:
    logger.info("Generating guided viz audio", extra={"email": email, "session_id": session_id, "mood": music_mood})

    voice_bytes, tts_chars = _build_voice_audio(script)

    logger.info("Mixing voice with local music", extra={"email": email, "mood": music_mood})
    final_bytes = _mix_voice_and_music(voice_bytes, music_mood)

    key = f"guided_viz_audio/{email}/{session_id}.mp3"
    url = upload_media(io.BytesIO(final_bytes), key, content_type="audio/mpeg")

    logger.info("Guided viz audio stored", extra={"email": email, "session_id": session_id, "url": url})
    return url, tts_chars


def _compute_cost(prompt_tokens: int, completion_tokens: int, tts_chars: int) -> dict:
    openai_usd = round(
        prompt_tokens * _OPENAI_INPUT_PER_TOKEN + completion_tokens * _OPENAI_OUTPUT_PER_TOKEN, 6
    )
    elevenlabs_usd = round(tts_chars * _ELEVENLABS_TTS_PER_CHAR, 6)
    return {
        "openai": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "estimated_usd": openai_usd,
        },
        "elevenlabs_tts": {
            "characters": tts_chars,
            "model": "eleven_multilingual_v2",
            "estimated_usd": elevenlabs_usd,
        },
        "total_estimated_usd": round(openai_usd + elevenlabs_usd, 6),
    }


def _build_user_context(email: str, message: str, username: str) -> str:
    parts = []
    if username:
        parts.append(f"User's name: {username}")
    try:
        ltm = get_memory(email, message)
        if ltm.get("long_term_memory"):
            parts.append(f"User's long-term memory:\n{ltm['long_term_memory']}")
    except Exception:
        pass
    try:
        journal = get_journal_context(email, message)
        if journal.get("journal_context"):
            parts.append(f"User's recent journal context:\n{journal['journal_context']}")
    except Exception:
        pass
    return "\n\n".join(parts)


def generate_guided_viz(email: str, message: str, session_id: str, username: str = "") -> None:
    """Background worker — runs after the route has already created the session and returned."""
    email = email.lower()
    logger.info("Guided viz background task started", extra={"email": email, "session_id": session_id})

    def _fail(reason: str, error_message: str) -> None:
        mark_session_error(session_id=session_id, error_message=error_message)
        event_bus.publish(email, {
            "type": "guided_viz_error",
            "title": "Visualization failed",
            "body": reason,
            "data": {"session_id": session_id},
        })

    try:
        user_context = _build_user_context(email, message, username)
        messages = [{"role": "system", "content": GUIDED_VIZ_SYSTEM_PROMPT}]
        if user_context:
            messages.append({"role": "system", "content": f"User context to personalise this session:\n\n{user_context}"})
        messages.append({"role": "user", "content": message})

        audio_url = None

        for iteration in range(MAX_TOOL_ITERATIONS):
            response = openai_client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages,
                tools=GUIDED_VIZ_TOOLS,
                tool_choice="required",
                temperature=1.0,
            )

            result = response.choices[0]

            if not result.message.tool_calls:
                logger.warning("Guided viz agent did not call tool", extra={"email": email, "iteration": iteration})
                break

            tool_call = result.message.tool_calls[0]
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments)

            logger.info("Guided viz tool call", extra={"email": email, "tool": func_name})

            if func_name == "generate_guided_viz_audio":
                script     = func_args.get("script", "")
                music_mood = func_args.get("music_mood", "grounding")
                theme      = func_args.get("theme", "")
                mood       = func_args.get("mood", "")
                tags       = func_args.get("tags", [])

                audio_url, tts_chars = _generate_and_store_audio(email, session_id, script, music_mood)

                usage = response.usage
                generation_cost = _compute_cost(
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    tts_chars=tts_chars,
                )

                logger.info("Guided viz cost", extra={"email": email, "cost": generation_cost})

                mark_session_complete(
                    session_id=session_id,
                    audio_url=audio_url,
                    theme=theme,
                    mood=mood,
                    tags=tags,
                    script=script,
                    generation_cost=generation_cost,
                )
                event_bus.publish(email, {
                    "type": "guided_viz_complete",
                    "title": "Your visualization is ready",
                    "body": "Tap to listen.",
                    "data": {"session_id": session_id, "audio_url": audio_url, "url": "https://app.regulatewithaura.com/visualization"},
                })
                return
            else:
                logger.warning("Unknown guided viz tool", extra={"email": email, "tool": func_name})
                break

        if not audio_url:
            logger.error("Guided viz completed without audio", extra={"email": email})
            _fail("Could not generate your visualization. Please try again.", "no audio produced")

    except Exception as e:
        logger.error("[generate_guided_viz] Error", extra={"email": email, "error": str(e)})
        _fail("Something went wrong. Please try again.", str(e))
