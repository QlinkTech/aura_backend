from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.utils.schema import PromptModel
from app.services.db.mongo_utils import return_system_prompt, update_system_prompt
from app.utils.logger_config import logger

prompt_router = APIRouter()


@prompt_router.get("/prompt")
def get_prompt():
    try:
        logger.info("Get system prompt request")
        response = return_system_prompt()
        if not response:
            return JSONResponse({"error": "System prompt not found"}, status_code=404)
        return response
    except Exception as e:
        raise e


@prompt_router.put("/prompt")
def update_prompt(data: PromptModel):
    try:
        logger.info("Update system prompt request")
        response = update_system_prompt(prompt=data.prompt)
        if response:
            logger.info("System prompt updated successfully")
            return JSONResponse({"success": True}, status_code=200)
        else:
            logger.warning("System prompt update returned no modified count")
            return JSONResponse({"success": False}, status_code=500)
    except Exception as e:
        raise e
