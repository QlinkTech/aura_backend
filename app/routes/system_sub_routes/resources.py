import io
import time
import uuid
from PIL import Image
from fastapi import APIRouter, BackgroundTasks, Body, File, Query, UploadFile
from fastapi.responses import JSONResponse
from bson import ObjectId
from app.services.db.mongo_utils import resources
from app.services.db.notification_utils import send_notification
from app.services.gupshup.notifications import broadcast_new_resource_whatsapp
from app.services.storage.r2_utils import generate_presigned_upload, delete_media, get_media_url, upload_media
from app.services import event_bus
from app.utils.logger_config import logger

THUMBNAIL_MAX_PX = 400
THUMBNAIL_QUALITY = 80

resources_router = APIRouter()

VALID_CATEGORIES = {"masterclass_vault", "downloadables", "audio"}

_CATEGORY_NOTIFICATION = {
    "masterclass_vault": ("New Masterclass Available", "A new masterclass has been added to the vault."),
    "downloadables":     ("New Download Available",    "A new resource is available to download."),
    "audio":             ("New Audio Available",       "A new audio has been added to your library."),
}


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


@resources_router.post("/resources/thumbnail")
def upload_thumbnail(file: UploadFile = File(...)):
    """Compress and upload a thumbnail to R2. Returns thumbnail_url and thumbnail_r2_key."""
    try:
        image = Image.open(io.BytesIO(file.file.read())).convert("RGB")
        image.thumbnail((THUMBNAIL_MAX_PX, THUMBNAIL_MAX_PX), Image.LANCZOS)

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=THUMBNAIL_QUALITY, optimize=True)
        buffer.seek(0)

        r2_key = f"thumbnails/{uuid.uuid4()}.jpg"
        url = upload_media(buffer, r2_key, content_type="image/jpeg")

        logger.info("Thumbnail uploaded", extra={"r2_key": r2_key})
        return {"thumbnail_url": url, "thumbnail_r2_key": r2_key}
    except Exception as e:
        logger.error("System: error uploading thumbnail", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


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
def list_resources(category: str = Query(None)):
    try:
        query = {"category": category} if category else {}
        docs = list(resources.find(query, {"r2_key": 0}).sort("created_at", -1))
        return {"resources": [_serialize(doc) for doc in docs]}
    except Exception as e:
        logger.error("System: error listing resources", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@resources_router.post("/resources")
def add_resource(background_tasks: BackgroundTasks, data: dict = Body(...)):
    """
    Step 2 — call this after the file has been uploaded to R2.
    Body: { "name": "...", "category": "masterclass_vault|downloadables|audio", "description": "...", "r2_key": "...", "url": "..." }
    """
    try:
        name = data.get("name")
        r2_key = data.get("r2_key")
        url = data.get("url")
        category = data.get("category", "")

        if not name or not r2_key or not url:
            return JSONResponse({"error": "name, r2_key and url are required"}, status_code=400)

        if category not in VALID_CATEGORIES:
            return JSONResponse(
                {"error": f"category must be one of: {', '.join(sorted(VALID_CATEGORIES))}"},
                status_code=400,
            )

        doc = {
            "name": name,
            "category": category,
            "url": url,
            "r2_key": r2_key,
            "description": data.get("description", ""),
            "thumbnail_url": data.get("thumbnail_url", ""),
            "thumbnail_r2_key": data.get("thumbnail_r2_key", ""),
            "created_at": int(time.time()),
        }
        result = resources.insert_one(doc)
        resource_id = str(result.inserted_id)
        logger.info("System: resource saved", extra={"id": resource_id, "category": category})

        title, body = _CATEGORY_NOTIFICATION[category]
        emails = send_notification(
            target="all",
            notif_type="new_resource",
            title=title,
            body=f"{name} — {body}" if name else body,
            data={"resource_id": resource_id, "category": category, "url": "https://app.regulatewithaura.com/resources"},
        )
        sse_payload = {
            "type": "new_resource",
            "title": title,
            "body": f"{name} — {body}" if name else body,
            "data": {"resource_id": resource_id, "category": category, "url": "https://app.regulatewithaura.com/resources"},
        }
        for email in emails:
            event_bus.publish(email, sse_payload)

        # Backgrounded — the broadcast sends serially to every recipient and must not hold the
        # admin's request open.
        background_tasks.add_task(broadcast_new_resource_whatsapp, name=name, category=category, resource_id=resource_id)

        return {"success": True, "id": resource_id}
    except Exception as e:
        logger.error("System: error saving resource", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@resources_router.put("/resources/{resource_id}")
def update_resource(resource_id: str, data: dict = Body(...)):
    try:
        allowed = {"name", "category", "description", "thumbnail_url", "thumbnail_r2_key"}
        update_fields = {k: v for k, v in data.items() if k in allowed}
        if not update_fields:
            return JSONResponse({"error": "No valid fields to update"}, status_code=400)

        if "category" in update_fields and update_fields["category"] not in VALID_CATEGORIES:
            return JSONResponse(
                {"error": f"category must be one of: {', '.join(sorted(VALID_CATEGORIES))}"},
                status_code=400,
            )

        if "thumbnail_r2_key" in update_fields:
            doc = resources.find_one({"_id": ObjectId(resource_id)}, {"thumbnail_r2_key": 1})
            if doc and doc.get("thumbnail_r2_key") and doc["thumbnail_r2_key"] != update_fields["thumbnail_r2_key"]:
                delete_media(doc["thumbnail_r2_key"])

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
        doc = resources.find_one({"_id": ObjectId(resource_id)}, {"r2_key": 1, "thumbnail_r2_key": 1})
        if not doc:
            return JSONResponse({"error": "Resource not found"}, status_code=404)

        delete_media(doc["r2_key"])
        if doc.get("thumbnail_r2_key"):
            delete_media(doc["thumbnail_r2_key"])

        resources.delete_one({"_id": ObjectId(resource_id)})

        logger.info("System: resource deleted", extra={"id": resource_id})
        return {"success": True}
    except Exception as e:
        logger.error("System: error deleting resource", extra={"id": resource_id, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)
