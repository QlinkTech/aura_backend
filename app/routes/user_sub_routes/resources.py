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
        # Browsing the library is not the same as opening something. These were
        # both logged as "resource_view", which left ~95% of that event type
        # carrying no content id and made real view counts meaningless.
        log_activity(current_user["email"], "resource_list_view")
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
        doc = resources.find_one({"_id": ObjectId(resource_id)}, {"r2_key": 0})
        if not doc:
            return JSONResponse({"error": "Resource not found"}, status_code=404)
        # Logged after the lookup — a 404 is not a view.
        log_activity(current_user["email"], "resource_view", ref_id=resource_id)
        return _serialize(doc)
    except Exception as e:
        logger.error("User: error fetching resource", extra={"id": resource_id, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@user_resources_router.post("/resources/{resource_id}/view")
def track_resource_view(resource_id: str, current_user=Depends(get_current_user)):
    """Record that this user opened this resource.

    The list response carries each resource's public file URL, so a client can
    play or download content without ever calling the detail endpoint. Without
    this beacon that consumption is invisible. Safe to call every time the user
    opens something — repeat calls are separate views by design.
    """
    try:
        if not resources.find_one({"_id": ObjectId(resource_id)}, {"_id": 1}):
            return JSONResponse({"error": "Resource not found"}, status_code=404)
        log_activity(current_user["email"], "resource_view", ref_id=resource_id)
        return {"success": True}
    except Exception as e:
        logger.error("User: error tracking resource view", extra={"id": resource_id, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)
