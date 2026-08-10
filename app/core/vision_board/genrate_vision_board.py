from openai import OpenAI
from app.utils.env_load import openai_api_key, cloud_api_key, cloud_api_secret, cloud_name
from app.services.mail.client import send_vision_board_ready_email
from app.services.gupshup.notifications import send_vision_board_ready_whatsapp
from app.core.vision_board.vision_board_prompt import build_prompt
from app.services.db.user_profile_utils import update_vision_board
from app.services.db.mongo_utils import user_profile
from app.utils.logger_config import logger
import cloudinary
import cloudinary.uploader

IMAGE_MODEL = "gpt-image-2-2026-04-21"

# ==== CLIENTS ====
openai_client = OpenAI(api_key=openai_api_key)

cloudinary.config(
    cloud_name=cloud_name,
    api_key=cloud_api_key,
    api_secret=cloud_api_secret
)


# ==== OPENAI IMAGE ====
def openai_image(prompt: str) -> str:
    logger.info("Generating image with OpenAI", extra={"model": IMAGE_MODEL})
    result = openai_client.images.generate(
        model=IMAGE_MODEL,
        prompt=prompt,
    )

    if not result.data or not result.data[0].b64_json:
        raise ValueError("OpenAI did not return an image")

    logger.info("OpenAI image generated successfully")
    return result.data[0].b64_json


# ==== CLOUDINARY UPLOAD ====
def cloudinary_upload(b64_image: str, email: str) -> str:
    logger.info("Uploading vision board to Cloudinary", extra={"email": email})
    data_uri = f"data:image/png;base64,{b64_image}"

    if not isinstance(email, str):
        logger.warning("Email is not str, converting", extra={"email": email, "type": type(email).__name__})
        email = str(email)

    upload_result = cloudinary.uploader.upload(
        data_uri,
        folder="vision_boards",
        public_id=f"{email}_vision",
        resource_type="image"
    )

    secure_url = upload_result["secure_url"]
    logger.info("Cloudinary upload successful", extra={"email": email, "url": secure_url})
    return secure_url


# ==== MAIN FUNCTION ====
def generate_vision_background(email: str, answers: dict, vibe: dict):
    try:
        logger.info("Starting vision board generation", extra={"email": email})

        #   Inject name from user profile
        user = user_profile.find_one({"email": email}, {"username": 1})
        answers["name"] = user.get("username", "") if user else ""

        #   Build Prompt
        prompt = build_prompt(answers=answers, vibe=vibe)
        if not isinstance(prompt, str):
            raise ValueError("Prompt is not a string! Got: " + str(type(prompt)))
        logger.info("Vision board prompt built successfully", extra={"email": email})

        #   OpenAI image generation
        b64_image = openai_image(prompt)

        #   Cloudinary
        secure_url = cloudinary_upload(b64_image, email)

        #   DB update
        update_vision_board(email=email, url=secure_url)
        logger.info("Vision board URL updated in DB", extra={"email": email, "url": secure_url})

        #   Mail
        try:
            name = answers.get("name", "")
            send_vision_board_ready_email(to_email=email, to_name=name)
            logger.info("Vision board ready email sent", extra={"email": email})
        except Exception as mail_err:
            logger.warning("Skipping email error", extra={"email": email, "error": str(mail_err)})

        #   WhatsApp (best-effort — never raises)
        send_vision_board_ready_whatsapp(email)

    except Exception as e:
        logger.error("Error in generate_vision_background", extra={"email": email, "error": str(e)})
        update_vision_board(email=email, url="failed")
