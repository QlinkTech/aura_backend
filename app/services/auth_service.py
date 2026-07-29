import time
from fastapi import HTTPException, status, Depends
from app.services.mail.client import send_trial_ended_email
from app.services.gupshup.lifecycle import send_trial_ended_whatsapp
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from jwt import decode, ExpiredSignatureError, InvalidTokenError
import jwt
from datetime import datetime, timedelta
import os
from app.services.db.mongo_utils import user_profile

from app.utils.env_load import secret_key

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60          # system/admin tokens (systems.py)
USER_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # end-user login/signup tokens

def hash_password(password):
    return pwd_context.hash(password)

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def create_access_token(data, expires_minutes=ACCESS_TOKEN_EXPIRE_MINUTES):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_ACTIVE_SUBSCRIPTION_STATUSES = {"active", "completed", "authenticated"}

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if "email" not in payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
        return {"email": payload["email"]}
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )

def get_system_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("role") != "system":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="System access only"
            )
        return payload
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )

def get_active_user(current_user: dict = Depends(get_current_user)):
    email = current_user["email"]
    user = user_profile.find_one({"email": email}, {"is_paid": 1, "is_bypassed": 1, "subscription_status": 1, "trial_end_at": 1, "paid_until": 1})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.get("is_bypassed"):
        return current_user

    now = int(time.time())
    paid_until = user.get("paid_until", 0)
    # A cancelled/paused/free status doesn't end access early if a paid-up period
    # (e.g. cancel-at-cycle-end) is still running — status means "won't renew".
    still_within_paid_period = bool(paid_until and now < paid_until)

    # Lazily revoke access for cancelled-mid-trial and free-plan users once their window passes
    if user.get("is_paid") and user.get("subscription_status") in ("cancelled", "paused", "free") and not still_within_paid_period:
        if now >= user.get("trial_end_at", 0):
            user_profile.update_one({"email": email}, {"$set": {"is_paid": False, "updated_at": now}})
            try:
                send_trial_ended_email(to_email=email)
                # remove_contact_from_list(email=email, list_id=LIST_TRIAL)
            except Exception:
                pass
            send_trial_ended_whatsapp(email=email)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active subscription required")

    if user.get("is_paid") or user.get("subscription_status") in _ACTIVE_SUBSCRIPTION_STATUSES or still_within_paid_period:
        return current_user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active subscription required")