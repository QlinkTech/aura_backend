from openai import OpenAI
from google import genai
from dotenv import load_dotenv
import os
import base64
import httpx

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

prompt = "A serene mountain landscape at sunrise, photorealistic, vibrant colors"

print("Generating image...")
response = client.images.generate(
    model="dall-e-3",
    prompt=prompt,
    size="1024x1024",
    response_format="url",
    n=1,
)

image_url = response.data[0].url
image_bytes = httpx.get(image_url).content
with open("test_output.png", "wb") as f:
    f.write(image_bytes)
print("✅ Image saved to test_output.png")


client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

prompt = "A serene mountain landscape at sunrise, photorealistic, vibrant colors"

print("Generating image...")
response = client.models.generate_content(
    model="gemini-3-pro-image-preview",
    contents=[prompt],
)

for part in response.parts:
    if part.text is not None:
        print("Text:", part.text)
    elif part.inline_data is not None:
        image_bytes = part.inline_data.data
        with open("test_output.png", "wb") as f:
            f.write(image_bytes)
        print("✅ Image saved to test_output.png")