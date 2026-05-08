import time
import secrets
from fastapi import HTTPException, status
from app.services.db.mongo_utils import user_profile, password_reset_tokens
from app.services.auth_service import hash_password, verify_password, create_access_token
from app.services.brevo.client import send_account_created_email, send_reset_password_email, add_registered_contact
from app.utils.env_load import frontend_url
from app.utils.logger_config import logger

RESET_TOKEN_EXPIRY_SECONDS = 3600  # 1 hour


def create_account(email: str, password: str, user_name: str, phone: str = ""):
    try:
        email = email.lower()
        logger.info("Creating account", extra={"email": email})
        existing = user_profile.find_one({"email": email})

        hashed_pw = hash_password(password)

        if existing:
            if existing.get("is_logged_in", True):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
            # Early bird user — stub profile exists, complete their account
            logger.info("Early bird user registering", extra={"email": email})
            user_profile.update_one(
                {"email": email},
                {"$set": {
                    "username": user_name,
                    "phone": phone,
                    "password": hashed_pw,
                    "chat_history": [],
                    "vision_board_url": "",
                    "is_logged_in": True,
                    "updated_at": int(time.time()),
                }}
            )
        else:
            user_profile.insert_one({
                "email": email,
                "username": user_name,
                "phone": phone,
                "password": hashed_pw,
                "chat_history": [],
                "vision_board_url": "",
                "is_paid": False,
                "is_logged_in": True,
                "created_at": int(time.time()),
                "updated_at": int(time.time())
            })

        token = create_access_token({"sub": email, "email": email})
        logger.info("Account created successfully", extra={"email": email})

        try:
            send_account_created_email(to_email=email, to_name=user_name)
            logger.info("Account created email sent", extra={"email": email})
        except Exception as e:
            logger.error("Failed to send account created email", extra={"email": email, "error": str(e)})

        try:
            add_registered_contact(email=email, name=user_name)
            logger.info("Contact added to registered list", extra={"email": email})
        except Exception as e:
            logger.error("Failed to add contact to registered list", extra={"email": email, "error": str(e)})

        return {"message": "Account created successfully", "access_token": token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating account", extra={"email": email, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def login(email: str, password: str):
    try:
        email = email.lower()
        logger.info("Login attempt", extra={"email": email})
        user = user_profile.find_one({"email": email})
        if not user or not user.get("password") or not verify_password(password, user["password"]):
            logger.warning("Login failed - invalid credentials or create your account.", extra={"email": email})
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        token = create_access_token({"sub": email, "email": email})
        logger.info("Login successful", extra={"email": email})
        return {"access_token": token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error during login", extra={"email": email, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ---------------- Chat History Utilities ---------------- #

def get_last_chat_history(email: str, limit: int = 10):
    try:
        user = user_profile.find_one({"email": email}, {"chat_history": 1})
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user.get("chat_history", [])[-limit:]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching last chat history", extra={"email": email, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def get_chat_history(email: str):
    try:
        user = user_profile.find_one({"email": email}, {"chat_history": 1})
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user.get("chat_history", [])
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching chat history", extra={"email": email, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def add_chat_history(email: str, role: str, content: str):
    try:
        chat_item = {
            "content": content,
            "role": role
        }
        result = user_profile.update_one(
            {"email": email},
            {"$push": {"chat_history": chat_item}, "$set": {"updated_at": int(time.time())}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return {"message": "Chat added successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error adding chat history", extra={"email": email, "role": role, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def update_vision_board(email: str, url: str):
    try:
        logger.info("Updating vision board URL", extra={"email": email, "url": url})
        result = user_profile.update_one(
            {"email": email},
            {"$set": {"vision_board_url": url, "updated_at": int(time.time())}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return {"message": "Vision board updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating vision board", extra={"email": email, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def get_user_details(email: str):
    try:
        user = user_profile.find_one({"email": email}, {"_id": 0, "chat_history": 0, "password": 0})
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching user details", extra={"email": email, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def check_user_exists(email: str):
    try:
        email = email.lower()
        user = user_profile.find_one({"email": email}, {"_id": 1})
        exists = user is not None
        logger.info("Check user exists", extra={"email": email, "exists": exists})
        return {"exists": exists}
    except Exception as e:
        logger.error("Error checking user existence", extra={"email": email, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def request_password_reset(email: str):
    try:
        email = email.lower()
        logger.info("Password reset requested", extra={"email": email})
        user = user_profile.find_one({"email": email}, {"username": 1})
        if not user:
            # Return success to avoid email enumeration
            return {"message": "If that email is registered, a reset link has been sent."}

        token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + RESET_TOKEN_EXPIRY_SECONDS

        password_reset_tokens.delete_many({"email": email})
        password_reset_tokens.insert_one({
            "email": email,
            "token": token,
            "expires_at": expires_at,
            "used": False,
        })

        reset_link = f"{frontend_url}/reset-password?token={token}"
        username = user.get("username", "")

        try:
            send_reset_password_email(to_email=email, to_name=username, reset_link=reset_link)
            logger.info("Password reset email sent", extra={"email": email})
        except Exception as e:
            logger.error("Failed to send reset password email", extra={"email": email, "error": str(e)})

        return {"message": "If that email is registered, a reset link has been sent."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing password reset request", extra={"email": email, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def reset_password(token: str, new_password: str):
    try:
        logger.info("Password reset attempt with token")
        record = password_reset_tokens.find_one({"token": token})

        if not record:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset link.")
        if record.get("used"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This reset link has already been used.")
        if int(time.time()) > record["expires_at"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This reset link has expired.")

        email = record["email"]
        hashed_pw = hash_password(new_password)
        user_profile.update_one(
            {"email": email},
            {"$set": {"password": hashed_pw, "updated_at": int(time.time())}}
        )
        password_reset_tokens.update_one({"token": token}, {"$set": {"used": True}})

        logger.info("Password reset successfully", extra={"email": email})
        return {"message": "Password reset successfully."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error resetting password", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
