from fastapi import APIRouter
from app.utils.schema import RegisterRequest, LoginRequest, CheckUserRequest, RequestResetPasswordRequest, ResetPasswordRequest
from app.services.db.user_profile_utils import create_account, login, check_user_exists, request_password_reset, reset_password
from app.utils.logger_config import logger

auth_router = APIRouter()

@auth_router.post("/register")
def register(payload: RegisterRequest):
    logger.info("Register request", extra={"email": payload.email})
    return create_account(payload.email, payload.password, payload.user_name)

@auth_router.post("/login")
def login_user(payload: LoginRequest):
    logger.info("Login request", extra={"email": payload.email})
    return login(payload.email, payload.password)

@auth_router.post("/check-user")
def check_user(payload: CheckUserRequest):
    logger.info("Check user request", extra={"email": payload.email})
    return check_user_exists(payload.email)

@auth_router.post("/request-reset-password")
def request_reset(payload: RequestResetPasswordRequest):
    logger.info("Password reset requested", extra={"email": payload.email})
    return request_password_reset(payload.email)

@auth_router.post("/reset-password")
def reset_user_password(payload: ResetPasswordRequest):
    logger.info("Reset password attempt")
    return reset_password(payload.token, payload.new_password)
