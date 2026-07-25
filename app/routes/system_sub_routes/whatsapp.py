from typing import Literal, Optional
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from app.utils.schema import CreateWhatsappTemplateModel, EditWhatsappTemplateModel, TriggerWhatsappCampaignModel
from app.services.gupshup.client import create_template, list_templates, edit_template, delete_template, upload_template_media
from app.services.db.whatsapp_campaign_utils import (
    create_campaign, run_campaign, send_campaign_messages, retry_campaign, get_campaign, list_campaigns,
    list_personalization_fields, get_campaign_contacts, cancel_campaign,
)
from app.utils.logger_config import logger

whatsapp_router = APIRouter()


@whatsapp_router.post("/whatsapp/templates")
def apply_for_template(payload: CreateWhatsappTemplateModel):
    """Apply for (create) a new WhatsApp message template via the Gupshup Partner API."""
    try:
        logger.info("System: applying for WhatsApp template", extra={"element_name": payload.element_name, "category": payload.category})
        result = create_template(payload)
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System: error creating WhatsApp template", extra={"element_name": payload.element_name, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@whatsapp_router.get("/whatsapp/templates")
def get_templates(
    template_type: Optional[str] = None,
    status: Optional[str] = None,
    stage: Optional[str] = None,
    useable: Optional[bool] = None,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    element_name: Optional[str] = None,
    data: Optional[str] = None,
    page_no: Optional[int] = None,
    page_size: Optional[int] = None,
):
    """List WhatsApp templates for the configured Gupshup app, with rejection reasons/miscategorization info."""
    try:
        params = {
            "templateType": template_type,
            "status": status,
            "stage": stage,
            "useable": useable,
            "startTime": start_time,
            "endTime": end_time,
            "elementName": element_name,
            "data": data,
            "pageNo": page_no,
            "pageSize": page_size,
        }
        logger.info("System: fetching WhatsApp templates", extra={k: v for k, v in params.items() if v is not None})
        return list_templates(params)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System: error fetching WhatsApp templates", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@whatsapp_router.put("/whatsapp/templates/{template_id}")
def update_template(template_id: str, payload: EditWhatsappTemplateModel):
    """Edit an existing WhatsApp template by templateId via the Gupshup Partner API."""
    try:
        logger.info("System: editing WhatsApp template", extra={"template_id": template_id})
        result = edit_template(template_id, payload)
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System: error editing WhatsApp template", extra={"template_id": template_id, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@whatsapp_router.delete("/whatsapp/templates/{element_name}")
def remove_template(element_name: str):
    """Permanently delete a WhatsApp template by elementName via the Gupshup Partner API. Irreversible."""
    try:
        logger.warning("System: deleting WhatsApp template", extra={"element_name": element_name})
        result = delete_template(element_name)
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System: error deleting WhatsApp template", extra={"element_name": element_name, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@whatsapp_router.post("/whatsapp/templates/media")
def upload_media(
    file_type: str = Form(..., description='MIME type, e.g. "image/png", "video/mp4", "application/pdf" — not a bare extension'),
    file: Optional[UploadFile] = File(None),
    file_url: Optional[str] = Form(None),
):
    """Upload sample media for a template, returning a handleId to pass as example_media when applying for a template."""
    try:
        if not file and not file_url:
            return JSONResponse({"error": "Either 'file' or 'file_url' must be provided"}, status_code=400)

        logger.info("System: uploading WhatsApp template media", extra={"file_type": file_type, "via_url": bool(file_url)})
        result = upload_template_media(
            file_type=file_type,
            file_bytes=file.file.read() if file else None,
            filename=file.filename if file else None,
            content_type=file.content_type if file else None,
            file_url=file_url,
        )
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System: error uploading WhatsApp template media", extra={"file_type": file_type, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@whatsapp_router.get("/whatsapp/campaigns/personalization-fields")
def get_personalization_fields():
    """User profile fields available for per-recipient params, e.g. {"field": "username", "fallback": "there"}."""
    try:
        return {"fields": list_personalization_fields()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System: error listing personalization fields", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@whatsapp_router.post("/whatsapp/campaigns")
def trigger_campaign(payload: TriggerWhatsappCampaignModel, background_tasks: BackgroundTasks):
    """Trigger a template-message campaign to all users or to specific engagement tiers. Sends run in the background, or later if scheduled_at is set."""
    try:
        logger.info("System: triggering WhatsApp campaign", extra={"campaign_name": payload.name, "target": payload.target, "tiers": payload.tiers, "numbers": len(payload.numbers or []), "scheduled_at": payload.scheduled_at})
        result = create_campaign(
            name=payload.name,
            template_id=payload.template_id,
            params=payload.params,
            target=payload.target,
            tiers=payload.tiers,
            numbers=payload.numbers,
            media_type=payload.media_type,
            media_url=payload.media_url,
            media_id=payload.media_id,
            scheduled_at=payload.scheduled_at,
        )
        if result["status"] != "scheduled":
            background_tasks.add_task(run_campaign, result["campaign_id"])
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System: error triggering WhatsApp campaign", extra={"campaign_name": payload.name, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@whatsapp_router.delete("/whatsapp/campaigns/{campaign_id}")
def cancel_campaign_route(campaign_id: str):
    """Cancels a campaign that hasn't sent yet. Only valid while the campaign is still 'scheduled'."""
    try:
        logger.info("System: cancelling WhatsApp campaign", extra={"campaign_id": campaign_id})
        return {"success": True, **cancel_campaign(campaign_id)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System: error cancelling WhatsApp campaign", extra={"campaign_id": campaign_id, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@whatsapp_router.post("/whatsapp/campaigns/{campaign_id}/retry")
def retry_campaign_route(campaign_id: str, filter: Literal["failed", "pending", "all"], background_tasks: BackgroundTasks):
    """Re-attempts sending on a subset of a campaign's recipients: 'failed' (only ones that errored),
    'pending' (never attempted, e.g. left over after an aborted run), or 'all' (both). Runs in the background."""
    try:
        logger.info("System: retrying WhatsApp campaign", extra={"campaign_id": campaign_id, "filter": filter})
        result = retry_campaign(campaign_id, filter)
        background_tasks.add_task(send_campaign_messages, campaign_id, result["statuses"])
        return {"success": True, "campaign_id": result["campaign_id"], "filter": result["filter"], "retrying": result["retrying"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System: error retrying WhatsApp campaign", extra={"campaign_id": campaign_id, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@whatsapp_router.get("/whatsapp/campaigns")
def get_campaigns():
    """List all campaigns, newest first, each with live delivery stats."""
    try:
        return {"campaigns": list_campaigns()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System: error listing WhatsApp campaigns", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@whatsapp_router.get("/whatsapp/campaigns/{campaign_id}")
def get_campaign_details(campaign_id: str):
    """Campaign detail with stats: pending, sent, delivered, read (seen), failed."""
    try:
        return get_campaign(campaign_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System: error fetching WhatsApp campaign", extra={"campaign_id": campaign_id, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@whatsapp_router.get("/whatsapp/campaigns/{campaign_id}/contacts")
def get_campaign_contacts_route(
    campaign_id: str,
    status: Optional[str] = None,
    page_no: int = 1,
    page_size: int = 50,
):
    """Per-contact delivery breakdown for a campaign — who received it, read it, failed, etc. Optionally filter by status: pending/sent/delivered/read/failed."""
    try:
        return get_campaign_contacts(campaign_id, status_filter=status, page_no=page_no, page_size=page_size)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System: error fetching WhatsApp campaign contacts", extra={"campaign_id": campaign_id, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)
