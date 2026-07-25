from pymongo import MongoClient
from app.utils.env_load import mongodb_uri
from app.utils.logger_config import logger

mongo_client = MongoClient(mongodb_uri)
db = mongo_client["aura"]
user_profile = db["user_profile"]
system = db["systems"]
payments = db["payments"]
journal_log = db["journal_log"]
password_reset_tokens = db["password_reset_tokens"]
resources = db["resources"]
eft_sessions = db["eft_sessions"]
chat_sessions = db["chat_sessions"]
masterclass = db["masterclass"]
guided_viz_sessions = db["guided_viz_sessions"]
notifications = db["notifications"]
activity_log = db["activity_log"]
phone_otps = db["phone_otps"]
whatsapp_campaigns = db["whatsapp_campaigns"]
whatsapp_campaign_messages = db["whatsapp_campaign_messages"]
whatsapp_template_media = db["whatsapp_template_media"]


def return_system_prompt():
    """Returns system prompt."""
    try:
        response = system.find_one({"category": "system_prompt"}, {"_id": 0})
        return response if response else None
    except Exception as e:
        logger.error("Error fetching system prompt", extra={"error": str(e)})
        raise e


def update_system_prompt(prompt: str):
    try:
        doc = system.find_one({"category": "system_prompt"})
        if not doc:
            return False

        previous_prompt = doc.get("prompt", "")

        update_fields = {
            "prompt": prompt,
            "old_prompt": previous_prompt
        }

        result = system.update_one(
            {"category": "system_prompt"},
            {"$set": update_fields},
            upsert=False
        )

        logger.info("System prompt updated", extra={"modified": result.modified_count > 0})
        return result.modified_count > 0

    except Exception as e:
        logger.error("Error updating system prompt", extra={"error": str(e)})
        raise e
