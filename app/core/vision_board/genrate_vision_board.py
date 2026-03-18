from openai import OpenAI
from app.utils.env_load import openai_api_key, cloud_api_key, cloud_api_secret, cloud_name
from app.utils.send_mail import send_vision_board_ready_email
from app.core.vision_board.vision_board_prompt import build_prompt
from app.utils.db.mongo_utils import update_vision_board
import cloudinary
import cloudinary.uploader
import base64
import httpx


# ==== CLIENTS ====
openai_client = OpenAI(api_key=openai_api_key)

cloudinary.config(
    cloud_name=cloud_name,
    api_key=cloud_api_key,
    api_secret=cloud_api_secret
)


# ==== OPENAI IMAGE ====
def openai_image(prompt: str) -> str:
    print("Generating image with OpenAI...")
    response = openai_client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        response_format="url",
        n=1,
    )

    image_url = response.data[0].url
    image_bytes = httpx.get(image_url).content
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    print("✅ OpenAI image generated")
    return b64_image


# ==== CLOUDINARY UPLOAD ====
def cloudinary_upload(b64_image: str, email: str) -> str:
    print("Uploading to Cloudinary...")
    data_uri = f"data:image/png;base64,{b64_image}"

    if not isinstance(email, str):
        print("⚠️ Email is not str, fixing:", email, type(email))
        email = str(email)

    print("DEBUG TYPES:", type(data_uri), type(email))

    upload_result = cloudinary.uploader.upload(
        data_uri,
        folder="vision_boards",
        public_id=f"{email}_vision",
        resource_type="image"
    )

    secure_url = upload_result["secure_url"]
    print("✅ Upload successful:", secure_url)
    return secure_url


# ==== MAIN FUNCTION ====
def generate_vision_background(email: str, answers: dict, vibe: dict):
    try:
        print("🚀 Starting vision board generation")

        #   Build Prompt
        prompt = build_prompt(answers=answers, vibe=vibe)
        if not isinstance(prompt, str):
            raise ValueError("Prompt is not a string! Got: " + str(type(prompt)))
        print("Prompt built successfully")

        #   OpenAI
        b64_image = openai_image(prompt)

        #   Cloudinary
        secure_url = cloudinary_upload(b64_image, email)

        #   DB update
        update_vision_board(email=email, url=secure_url)
        print("✅ Vision board URL updated in DB")

        #   Mail
        try:
            dashboard_link = "https://mmd-frontend.vercel.app/dashboard"
            send_vision_board_ready_email(email, dashboard_link)
            print("📩 Mail sent")
        except Exception as mail_err:
            print(f"⚠️ Skipping email error: {mail_err}")

    except Exception as e:
        print("❌ Error in generate_vision_background:", e)
        update_vision_board(email=email, url="failed")
