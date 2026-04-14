import time
import uuid
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from bson import ObjectId
from app.services.db.mongo_utils import resources
from app.services.storage.r2_utils import generate_presigned_upload, delete_media, get_media_url
from app.utils.env_load import r2_bucket
from app.utils.logger_config import logger

resources_router = APIRouter()


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


@resources_router.post("/resources/presigned-url")
def get_presigned_url(data: dict = Body(...)):
    """
    Step 1 — call this to get a presigned URL + r2_key before uploading.
    Body: { "filename": "video.mp4", "content_type": "video/mp4" }
    """
    try:
        filename = data.get("filename") or ""
        content_type = data.get("content_type") or "application/octet-stream"

        ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
        r2_key = f"resources/{uuid.uuid4()}.{ext}" if ext else f"resources/{uuid.uuid4()}"

        presigned_url = generate_presigned_upload(r2_key, content_type)
        public_url = get_media_url(r2_key)

        return {
            "upload_url": presigned_url,
            "r2_key": r2_key,
            "public_url": public_url,
        }
    except Exception as e:
        logger.error("System: error generating presigned URL", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@resources_router.get("/resources")
def list_resources():
    try:
        docs = list(resources.find({}, {"r2_key": 0}).sort("created_at", -1))
        return {"resources": [_serialize(doc) for doc in docs]}
    except Exception as e:
        logger.error("System: error listing resources", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@resources_router.post("/resources")
def add_resource(data: dict = Body(...)):
    """
    Step 2 — call this after the file has been uploaded to R2.
    Body: { "name": "...", "type": "...", "description": "...", "r2_key": "...", "url": "..." }
    """
    try:
        name = data.get("name")
        r2_key = data.get("r2_key")
        url = data.get("url")

        if not name or not r2_key or not url:
            return JSONResponse({"error": "name, r2_key and url are required"}, status_code=400)

        doc = {
            "name": name,
            "type": data.get("type", ""),
            "url": url,
            "r2_key": r2_key,
            "description": data.get("description", ""),
            "created_at": int(time.time()),
        }
        result = resources.insert_one(doc)
        logger.info("System: resource saved", extra={"id": str(result.inserted_id)})
        return {"success": True, "id": str(result.inserted_id)}
    except Exception as e:
        logger.error("System: error saving resource", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@resources_router.put("/resources/{resource_id}")
def update_resource(resource_id: str, data: dict = Body(...)):
    try:
        allowed = {"name", "type", "description"}
        update_fields = {k: v for k, v in data.items() if k in allowed}
        if not update_fields:
            return JSONResponse({"error": "No valid fields to update"}, status_code=400)

        result = resources.update_one(
            {"_id": ObjectId(resource_id)},
            {"$set": update_fields}
        )
        if result.matched_count == 0:
            return JSONResponse({"error": "Resource not found"}, status_code=404)

        logger.info("System: resource updated", extra={"id": resource_id})
        return {"success": True}
    except Exception as e:
        logger.error("System: error updating resource", extra={"id": resource_id, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@resources_router.delete("/resources/{resource_id}")
def delete_resource(resource_id: str):
    try:
        doc = resources.find_one({"_id": ObjectId(resource_id)}, {"r2_key": 1})
        if not doc:
            return JSONResponse({"error": "Resource not found"}, status_code=404)

        delete_media(doc["r2_key"])
        resources.delete_one({"_id": ObjectId(resource_id)})

        logger.info("System: resource deleted", extra={"id": resource_id})
        return {"success": True}
    except Exception as e:
        logger.error("System: error deleting resource", extra={"id": resource_id, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)
