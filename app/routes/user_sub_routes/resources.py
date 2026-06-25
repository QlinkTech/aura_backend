from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from bson import ObjectId
from app.services.auth_service import get_current_user
from app.services.db.mongo_utils import resources
from app.services.db.activity_log_utils import log_activity
from app.utils.logger_config import logger

user_resources_router = APIRouter()


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


@user_resources_router.get("/resources")
def list_resources(
    category: str = Query(None, description="Filter by category, omit for all"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    try:
        log_activity(current_user["email"], "resource_view")
        query = {} if not category or category.lower() == "all" else {"category": category}
        skip = (page - 1) * limit
        total = resources.count_documents(query)
        docs = list(resources.find(query, {"r2_key": 0}).sort("created_at", -1).skip(skip).limit(limit))
        return {
            "resources": [_serialize(doc) for doc in docs],
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit,
        }
    except Exception as e:
        logger.error("User: error listing resources", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@user_resources_router.get("/resources/{resource_id}")
def get_resource(resource_id: str, current_user=Depends(get_current_user)):
    try:
        log_activity(current_user["email"], "resource_view", ref_id=resource_id)
        doc = resources.find_one({"_id": ObjectId(resource_id)}, {"r2_key": 0})
        if not doc:
            return JSONResponse({"error": "Resource not found"}, status_code=404)
        return _serialize(doc)
    except Exception as e:
        logger.error("User: error fetching resource", extra={"id": resource_id, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)
