from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from app.utils.schema import SendWhatsappReplyModel
from app.services.auth_service import get_system_user
from app.services.db.whatsapp_inbox_utils import (
    list_conversations, get_conversation_messages, mark_conversation_read, send_reply,
)
from app.utils.logger_config import logger

whatsapp_inbox_router = APIRouter()


@whatsapp_inbox_router.get("/whatsapp/inbox/conversations")
def get_conversations(search: Optional[str] = None, page_no: int = 1, page_size: int = 50):
    """List WhatsApp conversations, most recently active first, each with unread count and 24h-window status."""
    try:
        return list_conversations(search=search, page_no=page_no, page_size=page_size)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System: error listing WhatsApp conversations", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@whatsapp_inbox_router.get("/whatsapp/inbox/conversations/{phone}/messages")
def get_messages(phone: str, page_no: int = 1, page_size: int = 50):
    """Full message thread for one phone number, chronological (oldest first)."""
    try:
        return get_conversation_messages(phone, page_no=page_no, page_size=page_size)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System: error fetching WhatsApp conversation messages", extra={"phone": phone, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@whatsapp_inbox_router.post("/whatsapp/inbox/conversations/{phone}/read")
def mark_read(phone: str):
    """Resets the unread count for a conversation."""
    try:
        return mark_conversation_read(phone)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System: error marking WhatsApp conversation read", extra={"phone": phone, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@whatsapp_inbox_router.post("/whatsapp/inbox/conversations/{phone}/reply")
def reply(phone: str, payload: SendWhatsappReplyModel, system_user: dict = Depends(get_system_user)):
    """Sends a free-form text reply. Only works while the 24h customer-service window is open —
    returns 400 with the approved-template list attached if it's closed."""
    try:
        logger.info("System: sending WhatsApp inbox reply", extra={"phone": phone, "admin": system_user.get("sub")})
        return send_reply(phone, payload.text, admin_username=system_user.get("sub"))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System: error sending WhatsApp inbox reply", extra={"phone": phone, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)
