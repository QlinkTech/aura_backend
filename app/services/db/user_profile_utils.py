import time
import secrets
import requests as http_requests
from fastapi import HTTPException, status
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from app.services.db.mongo_utils import user_profile, password_reset_tokens
from app.services.auth_service import hash_password, verify_password, create_access_token, USER_ACCESS_TOKEN_EXPIRE_MINUTES, revoke_access_if_lapsed
from app.services.mail.client import send_account_created_email, send_reset_password_email
from app.utils.env_load import frontend_url, google_client_id, google_client_secret
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

        token = create_access_token({"sub": email, "email": email}, expires_minutes=USER_ACCESS_TOKEN_EXPIRE_MINUTES)
        logger.info("Account created successfully", extra={"email": email})

        try:
            send_account_created_email(to_email=email, to_name=user_name)
            logger.info("Account created email sent", extra={"email": email})
        except Exception as e:
            logger.error("Failed to send account created email", extra={"email": email, "error": str(e)})

        # try:
        #     add_registered_contact(email=email, name=user_name)
        #     logger.info("Contact added to registered list", extra={"email": email})
        # except Exception as e:
        #     logger.error("Failed to add contact to registered list", extra={"email": email, "error": str(e)})

        return {"message": "Account created successfully", "access_token": token, "token_type": "bearer", "phone_verified": False}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating account", extra={"email": email, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def google_login(id_token: str):
    try:
        if not google_client_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Google auth not configured")

        idinfo = google_id_token.verify_oauth2_token(
            id_token,
            google_requests.Request(),
            google_client_id,
        )

        email = idinfo.get("email", "").lower()
        if not email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google token missing email")

        first_name = idinfo.get("given_name", "")
        last_name = idinfo.get("family_name", "")
        full_name = f"{first_name} {last_name}".strip() or email.split("@")[0]
        picture = idinfo.get("picture", "")

        logger.info("Google login attempt", extra={"email": email})

        user = user_profile.find_one({"email": email})
        if user:
            # Lazy expiry check — honours paid_until, skips bypassed users
            revoke_access_if_lapsed(email, user)
            logger.info("Existing user logged in via Google", extra={"email": email})
        else:
            user_profile.insert_one({
                "email": email,
                "username": full_name,
                "phone": "",
                "password": None,
                "chat_history": [],
                "vision_board_url": "",
                "profile_picture": picture,
                "is_paid": False,
                "is_logged_in": True,
                "auth_provider": "google",
                "created_at": int(time.time()),
                "updated_at": int(time.time()),
            })
            logger.info("New user created via Google", extra={"email": email})
            try:
                send_account_created_email(to_email=email, to_name=full_name)
                # add_registered_contact(email=email, name=full_name)
            except Exception as e:
                logger.error("Failed to send account created email", extra={"email": email, "error": str(e)})

        token = create_access_token({"sub": email, "email": email}, expires_minutes=USER_ACCESS_TOKEN_EXPIRE_MINUTES)
        return {
            "access_token": token,
            "token_type": "bearer",
            "email": email,
            "name": full_name,
            "picture": picture,
            "is_new_user": user is None,
            "phone_verified": bool(user.get("phone_verified", False)) if user else False,
        }
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Invalid Google token", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")
    except Exception as e:
        logger.error("Error during Google login", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
ALLOWED_REDIRECT_URIS = {
    "https://app.regulatewithaura.com/api/auth/callback/google",
    "http://localhost:3000/api/auth/callback/google",
}

def google_code_login(code: str, redirect_uri: str):
    try:
        if not google_client_id or not google_client_secret:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Google auth not configured")

        if redirect_uri not in ALLOWED_REDIRECT_URIS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid redirect URI")

        # Exchange authorization code for tokens
        token_response = http_requests.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": google_client_id,
            "client_secret": google_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })

        if not token_response.ok:
            logger.warning("Google token exchange failed", extra={"status": token_response.status_code, "body": token_response.text})
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Failed to exchange Google authorization code")

        token_data = token_response.json()
        raw_id_token = token_data.get("id_token")
        if not raw_id_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No ID token returned from Google")

        # Verify the ID token
        idinfo = google_id_token.verify_oauth2_token(
            raw_id_token,
            google_requests.Request(),
            google_client_id,
        )

        email = idinfo.get("email", "").lower()
        if not email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google token missing email")

        first_name = idinfo.get("given_name", "")
        last_name = idinfo.get("family_name", "")
        full_name = f"{first_name} {last_name}".strip() or email.split("@")[0]
        picture = idinfo.get("picture", "")

        logger.info("Google code login attempt", extra={"email": email})

        user = user_profile.find_one({"email": email})
        if user:
            revoke_access_if_lapsed(email, user)
            logger.info("Existing user logged in via Google code flow", extra={"email": email})
        else:
            user_profile.insert_one({
                "email": email,
                "username": full_name,
                "phone": "",
                "password": None,
                "chat_history": [],
                "vision_board_url": "",
                "profile_picture": picture,
                "is_paid": False,
                "is_logged_in": True,
                "auth_provider": "google",
                "created_at": int(time.time()),
                "updated_at": int(time.time()),
            })
            logger.info("New user created via Google code flow", extra={"email": email})
            try:
                send_account_created_email(to_email=email, to_name=full_name)
                # add_registered_contact(email=email, name=full_name)
            except Exception as e:
                logger.error("Failed to send account created email", extra={"email": email, "error": str(e)})

        token = create_access_token({"sub": email, "email": email}, expires_minutes=USER_ACCESS_TOKEN_EXPIRE_MINUTES)
        return {
            "access_token": token,
            "token_type": "bearer",
            "email": email,
            "name": full_name,
            "picture": picture,
            "is_new_user": user is None,
            "phone_verified": bool(user.get("phone_verified", False)) if user else False,
        }
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Invalid Google ID token in code flow", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")
    except Exception as e:
        logger.error("Error during Google code login", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def login(email: str, password: str):
    try:
        email = email.lower()
        logger.info("Login attempt", extra={"email": email})
        user = user_profile.find_one({"email": email})
        if not user or not user.get("password") or not verify_password(password, user["password"]):
            logger.warning("Login failed - invalid credentials or create your account.", extra={"email": email})
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        revoke_access_if_lapsed(email, user)

        token = create_access_token({"sub": email, "email": email}, expires_minutes=USER_ACCESS_TOKEN_EXPIRE_MINUTES)
        logger.info("Login successful", extra={"email": email})
        return {"access_token": token, "token_type": "bearer", "phone_verified": bool(user.get("phone_verified", False))}
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
