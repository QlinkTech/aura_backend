import time
from typing import Optional
from app.services.db.mongo_utils import whatsapp_template_media
from app.utils.logger_config import logger


def save_template_media(template_id: str, media_type: str, media_url: str, element_name: str = None) -> None:
    """Stores the default send-time media for a template, keyed by its Gupshup template id."""
    update = {"media_type": media_type, "media_url": media_url, "updated_at": int(time.time())}
    if element_name:
        update["element_name"] = element_name

    whatsapp_template_media.update_one({"template_id": template_id}, {"$set": update}, upsert=True)
    logger.info("Stored default send media for template", extra={"template_id": template_id, "element_name": element_name, "media_type": media_type})


def get_template_media(template_id: str) -> Optional[dict]:
    """Returns {"media_type", "media_url"} for a template if a default was stored, else None."""
    return whatsapp_template_media.find_one({"template_id": template_id}, {"_id": 0, "media_type": 1, "media_url": 1}) or None
