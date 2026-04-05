from google import genai
from google.genai import types
from app.utils.env_load import gemini_api_key, cloud_api_key, cloud_api_secret, cloud_name
from app.services.brevo.client import send_vision_board_ready_email
from app.core.vision_board.vision_board_prompt import build_prompt
from app.services.db.user_profile_utils import update_vision_board
from app.services.db.mongo_utils import user_profile
from app.utils.logger_config import logger
import cloudinary
import cloudinary.uploader
import base64


# ==== CLIENTS ====
gemini_client = genai.Client(api_key=gemini_api_key)

cloudinary.config(
    cloud_name=cloud_name,
    api_key=cloud_api_key,
    api_secret=cloud_api_secret
)


# ==== GEMINI IMAGE ====
def gemini_image(prompt: str) -> str:
    logger.info("Generating image with Gemini")
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)],
        ),
    ]
    config = types.GenerateContentConfig(
        response_modalities=["IMAGE", "TEXT"],
    )

    for chunk in gemini_client.models.generate_content_stream(
        model="gemini-2.5-flash-image",
        contents=contents,
        config=config,
    ):
        if not chunk.candidates:
            continue
        parts = chunk.candidates[0].content.parts
        if not parts:
            continue
        for part in parts:
            if part.inline_data and part.inline_data.data:
                b64_image = base64.b64encode(part.inline_data.data).decode("utf-8")
                logger.info("Gemini image generated successfully")
                return b64_image

    raise ValueError("Gemini did not return an image")


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

        #   Gemini
        b64_image = gemini_image(prompt)

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

    except Exception as e:
        logger.error("Error in generate_vision_background", extra={"email": email, "error": str(e)})
        update_vision_board(email=email, url="failed")
