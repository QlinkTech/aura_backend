import mimetypes
import os
import base64
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()


def generate():
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    prompt = "A serene mountain landscape at sunrise, photorealistic, vibrant colors"

    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)],
        ),
    ]

    generate_content_config = types.GenerateContentConfig(
        response_modalities=["IMAGE", "TEXT"],
    )

    print("Generating image with Gemini...")

    file_index = 0
    for chunk in client.models.generate_content_stream(
        model="gemini-2.5-flash-image",
        contents=contents,
        config=generate_content_config,
    ):
        if not chunk.candidates:
            continue

        parts = chunk.candidates[0].content.parts
        if not parts:
            continue

        for part in parts:
            if part.inline_data and part.inline_data.data:
                inline_data = part.inline_data
                file_extension = mimetypes.guess_extension(inline_data.mime_type)
                file_name = f"test_output_{file_index}{file_extension}"
                with open(file_name, "wb") as f:
                    f.write(inline_data.data)
                print(f"✅ Image saved to {file_name}")
                file_index += 1
            elif part.text:
                print("Text:", part.text)


if __name__ == "__main__":
    generate()
