from fastapi import APIRouter
from app.routes.user_sub_routes.profile import profile_router
from app.routes.user_sub_routes.chat import chat_router
from app.routes.user_sub_routes.vision import vision_router
from app.routes.user_sub_routes.voice import voice_router
from app.routes.user_sub_routes.journal import journal_router
from app.routes.user_sub_routes.resources import user_resources_router
from app.routes.user_sub_routes.eft import eft_router

user_router = APIRouter()

user_router.include_router(profile_router)
user_router.include_router(chat_router)
user_router.include_router(vision_router)
user_router.include_router(voice_router)
user_router.include_router(journal_router)
user_router.include_router(user_resources_router)
user_router.include_router(eft_router)
