from fastapi import APIRouter, BackgroundTasks
from app.utils.schema import RegisterRequest, LoginRequest, GenerateVisionModel, CheckUserRequest, ResetPasswordRequest
from app.utils.db.mongo_utils import create_account, login, update_vision_board, hash_password, create_access_token, check_user_exists, reset_password
from app.core.vision_board.genrate_vision_board import generate_vision_background
from app.utils.logger_config import logger

auth_router = APIRouter()

@auth_router.post("/register")
def register(payload: RegisterRequest):
    logger.info("Register request", extra={"email": payload.email})
    return create_account(payload.email, payload.password)

@auth_router.post("/login")
def login_user(payload: LoginRequest):
    logger.info("Login request", extra={"email": payload.email})
    return login(payload.email, payload.password)

@auth_router.post("/generate-vision")
def generate_vision(data: GenerateVisionModel, background_tasks: BackgroundTasks):
    logger.info("Generate vision request", extra={"email": data.email, "name": data.name})
    email = data.email.lower()
    hashed_pw = hash_password(data.password)

    # Update password and set vision_board_url as "preparing"
    from app.utils.db.mongo_utils import user_profile  # access Mongo collection
    from datetime import datetime
    user_profile.update_one(
        {"email": email},
        {
            "$set": {"password": hashed_pw, "updated_at": datetime.utcnow()},
            "$setOnInsert": {
                "chat_history": [],
                "name": data.name,
                "vision_board_url": "",
                "created_at": datetime.utcnow()
            }
        },
        upsert=True
    )

    update_vision_board(email, "preparing")
    access_token = create_access_token({"sub": email, "email": email})

    # Fire & forget vision board generation
    background_tasks.add_task(generate_vision_background, email, data.answers, data.vibe)
    logger.info("Vision board generation queued", extra={"email": email})

    return {"access_token": access_token, "token_type": "bearer"}

@auth_router.post("/check-user")
def check_user(payload: CheckUserRequest):
    logger.info("Check user request", extra={"email": payload.email})
    return check_user_exists(payload.email)

@auth_router.post("/reset-password")
def reset_user_password(payload: ResetPasswordRequest):
    logger.info("Reset password request", extra={"email": payload.email})
    return reset_password(payload.email, payload.new_password)
