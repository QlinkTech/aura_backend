from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from bson import ObjectId
from app.services.auth_service import get_current_user
from app.services.db.mongo_utils import resources
from app.utils.logger_config import logger

user_resources_router = APIRouter()


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


@user_resources_router.get("/resources")
def list_resources(current_user=Depends(get_current_user)):
    try:
        docs = list(resources.find({}, {"r2_key": 0}).sort("created_at", -1))
        return {"resources": [_serialize(doc) for doc in docs]}
    except Exception as e:
        logger.error("User: error listing resources", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@user_resources_router.get("/resources/{resource_id}")
def get_resource(resource_id: str, current_user=Depends(get_current_user)):
    try:
        doc = resources.find_one({"_id": ObjectId(resource_id)}, {"r2_key": 0})
        if not doc:
            return JSONResponse({"error": "Resource not found"}, status_code=404)
        return _serialize(doc)
    except Exception as e:
        logger.error("User: error fetching resource", extra={"id": resource_id, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)
