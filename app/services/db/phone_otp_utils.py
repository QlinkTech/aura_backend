import re
import secrets
import time

from fastapi import HTTPException, status
from app.services.db.mongo_utils import phone_otps, user_profile
from app.services.gupshup.client import send_otp_template
from app.utils.logger_config import logger

OTP_EXPIRY_SECONDS = 300       # 5 minutes
RESEND_COOLDOWN_SECONDS = 60
MAX_VERIFY_ATTEMPTS = 5


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid phone number")
    return digits


def send_phone_otp(email: str, phone: str) -> dict:
    phone = _normalize_phone(phone)
    logger.info("Phone OTP requested", extra={"email": email, "phone": phone})

    existing = phone_otps.find_one({"email": email}, sort=[("created_at", -1)])
    if existing and int(time.time()) - existing["created_at"] < RESEND_COOLDOWN_SECONDS:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Please wait before requesting another OTP.")

    otp = f"{secrets.randbelow(1_000_000):06d}"

    phone_otps.delete_many({"email": email})
    phone_otps.insert_one({
        "email": email,
        "phone": phone,
        "otp": otp,
        "attempts": 0,
        "created_at": int(time.time()),
        "expires_at": int(time.time()) + OTP_EXPIRY_SECONDS,
    })

    send_otp_template(phone_number=phone, otp_code=otp)

    return {"message": "OTP sent to your WhatsApp number."}


def verify_phone_otp(email: str, phone: str, otp: str) -> dict:
    phone = _normalize_phone(phone)
    record = phone_otps.find_one({"email": email, "phone": phone})

    if not record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No OTP request found for this number. Please request a new one.")

    if record["attempts"] >= MAX_VERIFY_ATTEMPTS:
        phone_otps.delete_one({"_id": record["_id"]})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Too many incorrect attempts. Please request a new OTP.")

    if int(time.time()) > record["expires_at"]:
        phone_otps.delete_one({"_id": record["_id"]})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This OTP has expired. Please request a new one.")

    if otp != record["otp"]:
        phone_otps.update_one({"_id": record["_id"]}, {"$inc": {"attempts": 1}})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect OTP.")

    phone_otps.delete_one({"_id": record["_id"]})
    user_profile.update_one(
        {"email": email},
        {"$set": {"phone": phone, "phone_verified": True, "updated_at": int(time.time())}}
    )

    logger.info("Phone number verified", extra={"email": email, "phone": phone})
    return {"message": "Phone number verified successfully.", "phone": phone}
