from typing import Optional
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from app.utils.schema import CreateWhatsappTemplateModel, EditWhatsappTemplateModel, TriggerWhatsappCampaignModel
from app.services.gupshup.client import create_template, list_templates, edit_template, delete_template, upload_template_media
from app.services.db.whatsapp_campaign_utils import create_campaign, run_campaign, get_campaign, list_campaigns
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
    file_type: str = Form(...),
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


@whatsapp_router.post("/whatsapp/campaigns")
def trigger_campaign(payload: TriggerWhatsappCampaignModel, background_tasks: BackgroundTasks):
    """Trigger a template-message campaign to all users or to specific engagement tiers. Sends run in the background."""
    try:
        logger.info("System: triggering WhatsApp campaign", extra={"name": payload.name, "target": payload.target, "tiers": payload.tiers})
        result = create_campaign(
            name=payload.name,
            template_id=payload.template_id,
            params=payload.params,
            target=payload.target,
            tiers=payload.tiers,
        )
        background_tasks.add_task(run_campaign, result["campaign_id"])
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("System: error triggering WhatsApp campaign", extra={"name": payload.name, "error": str(e)})
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
