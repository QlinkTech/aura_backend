"""
Quick test: renders a short guided viz script with en-IN accent and saves to test_output.mp3
Run from project root: python test_guided_viz_voice.py
"""
import os
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()

VOICE_ID = "hnMOqbQV1aV5iom08kJd"
TEST_SCRIPT = (
    "Close your eyes and take a slow, deep breath. "
    "Feel your body becoming heavy and relaxed. "
    "Imagine yourself in a peaceful place, safe and at ease. "
    "With every breath, you release all tension and worry."
)

client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

print("Generating with en-IN accent...")
chunks = client.text_to_speech.convert(
    voice_id=VOICE_ID,
    text=TEST_SCRIPT,
    model_id="eleven_multilingual_v2",
    output_format="mp3_44100_128",
    language_code="en-IN",
)
audio = b"".join(chunks)
with open("test_output_indian.mp3", "wb") as f:
    f.write(audio)
print(f"Saved: test_output_indian.mp3  ({len(audio):,} bytes)")

print("\nGenerating without language_code (default / auto-detect)...")
chunks = client.text_to_speech.convert(
    voice_id=VOICE_ID,
    text=TEST_SCRIPT,
    model_id="eleven_multilingual_v2",
    output_format="mp3_44100_128",
)
audio = b"".join(chunks)
with open("test_output_default.mp3", "wb") as f:
    f.write(audio)
print(f"Saved: test_output_default.mp3  ({len(audio):,} bytes)")

print("\nDone. Compare both files to confirm the accent difference.")
