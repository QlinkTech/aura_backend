from fastapi import APIRouter, Depends
from app.services.auth_service import get_active_user
from app.services.db.mongo_utils import masterclass as masterclass_col
from app.utils.logger_config import logger

masterclass_user_router = APIRouter()

_FILTER = {"_type": "masterclass"}


@masterclass_user_router.get("/masterclass")
def get_masterclass(current_user=Depends(get_active_user)):
    """Return the upcoming masterclass, or null if none is scheduled."""
    email = current_user["email"]
    try:
        doc = masterclass_col.find_one(_FILTER, {"_id": 0, "_type": 0})
        logger.info("Masterclass fetched", extra={"email": email})
        return {"masterclass": doc or None}
    except Exception as e:
        logger.error("Error fetching masterclass", extra={"email": email, "error": str(e)})
        return {"masterclass": None}
