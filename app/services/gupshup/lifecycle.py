from app.services.db.mongo_utils import user_profile
from app.services.gupshup.client import send_template_message
from app.utils.logger_config import logger

# Approved lifecycle templates (see test/emails_n_messages.txt for the copy).
# Both take a single {{1}} param: the user's name.
WELCOME_TEMPLATE_ID = "a36197f0-a19c-4358-9ed0-a27fa0bec616"       # "aura_welcome"
TRIAL_ENDED_TEMPLATE_ID = "9f43f530-81a1-4e57-907e-6f3f3f5bc9c3"   # "aura_trial_ending"

_NAME_FALLBACK = "there"


def send_welcome_whatsapp(phone_number: str, name: str = "") -> None:
    """Best-effort send of the welcome template right after phone verification.

    Never raises — a WhatsApp failure must not break the OTP verification flow."""
    try:
        message_id = send_template_message(
            phone_number=phone_number,
            template_id=WELCOME_TEMPLATE_ID,
            params=[name.strip() or _NAME_FALLBACK],
        )
        logger.info("Welcome WhatsApp sent", extra={"phone_number": phone_number, "message_id": message_id})
    except Exception as e:
        logger.error("Failed to send welcome WhatsApp", extra={"phone_number": phone_number, "error": str(e)})


def send_trial_ended_whatsapp(email: str) -> None:
    """Best-effort send of the trial-ended template to the user's verified WhatsApp number.

    Skips silently when the user never verified a phone number. Never raises —
    callers fire this alongside the trial-ended email and must not be interrupted."""
    try:
        user = user_profile.find_one({"email": email}, {"username": 1, "phone": 1, "phone_verified": 1})
        if not user or not user.get("phone_verified") or not user.get("phone"):
            logger.info("Trial ended WhatsApp skipped — no verified phone", extra={"email": email})
            return
        message_id = send_template_message(
            phone_number=user["phone"],
            template_id=TRIAL_ENDED_TEMPLATE_ID,
            params=[(user.get("username") or "").strip() or _NAME_FALLBACK],
        )
        logger.info("Trial ended WhatsApp sent", extra={"email": email, "message_id": message_id})
    except Exception as e:
        logger.error("Failed to send trial ended WhatsApp", extra={"email": email, "error": str(e)})
