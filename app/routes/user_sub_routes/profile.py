from fastapi import APIRouter, Depends
from app.services.auth_service import get_active_user, get_current_user
from app.services.db.user_profile_utils import get_user_details
from app.utils.logger_config import logger

profile_router = APIRouter()


@profile_router.get("/user-profile")
def get_user(current_user=Depends(get_current_user)):
    email = current_user["email"]
    logger.info("Get user profile request", extra={"email": email})
    return get_user_details(email=email)
