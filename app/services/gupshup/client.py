import json
import requests
from fastapi import HTTPException, status
from app.utils.constants import GUPSHUP_SOURCE
from app.utils.env_load import gupshup_app_id, gupshup_app_name, gupshup_token
from app.utils.logger_config import logger

OTP_TEMPLATE_ID = "5a65995b-bd1b-4cfc-bff7-89f766b9fd8c"  # "otp3" approved authentication template


def send_otp_template(phone_number: str, otp_code: str) -> None:
    """Sends the approved 'otp_fom3' WhatsApp authentication template with the OTP code."""
    if not gupshup_app_id or not gupshup_token or not gupshup_app_name:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="WhatsApp OTP service not configured")

    logger.info("Sending OTP template", extra={"phone_number": phone_number})

    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/template/msg"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "token": gupshup_token,
    }
    data = {
        "source": GUPSHUP_SOURCE,
        "destination": phone_number,
        "src.name": gupshup_app_name,
        "template": json.dumps({
            "id": OTP_TEMPLATE_ID,
            "params": [otp_code, otp_code],
        }),
    }

    response = requests.post(url, headers=headers, data=data, timeout=10)
    if not response.ok:
        logger.error("Gupshup OTP send failed", extra={"phone_number": phone_number, "status": response.status_code, "body": response.text})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to send OTP via WhatsApp")

    logger.info("OTP template sent", extra={"phone_number": phone_number, "response": response.json()})
