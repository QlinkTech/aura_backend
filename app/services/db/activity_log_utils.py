import time
from app.services.db.mongo_utils import activity_log
from app.utils.logger_config import logger


def log_activity(email: str, activity_type: str, ref_id: str = None):
    try:
        activity_log.insert_one({
            "email": email.lower(),
            "type": activity_type,
            "ref_id": ref_id,
            "created_at": int(time.time()),
        })
    except Exception as e:
        logger.error("Failed to log activity", extra={"email": email, "type": activity_type, "error": str(e)})
