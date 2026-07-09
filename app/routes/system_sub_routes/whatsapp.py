from typing import Optional
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from app.utils.schema import CreateWhatsappTemplateModel, EditWhatsappTemplateModel
from app.services.gupshup.client import create_template, list_templates, edit_template, delete_template, upload_template_media
from app.utils.logger_config import logger

whatsapp_router = APIRouter()


@whatsapp_router.post("/whatsapp/templates")
def apply_for_template(payload: CreateWhatsappTemplateModel):
    """Apply for (create) a new WhatsApp message template via the Gupshup Partner API."""
    logger.info("System: applying for WhatsApp template", extra={"element_name": payload.element_name, "category": payload.category})
    result = create_template(payload)
    return {"success": True, **result}


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


@whatsapp_router.put("/whatsapp/templates/{template_id}")
def update_template(template_id: str, payload: EditWhatsappTemplateModel):
    """Edit an existing WhatsApp template by templateId via the Gupshup Partner API."""
    logger.info("System: editing WhatsApp template", extra={"template_id": template_id})
    result = edit_template(template_id, payload)
    return {"success": True, **result}


@whatsapp_router.delete("/whatsapp/templates/{element_name}")
def remove_template(element_name: str):
    """Permanently delete a WhatsApp template by elementName via the Gupshup Partner API. Irreversible."""
    logger.warning("System: deleting WhatsApp template", extra={"element_name": element_name})
    result = delete_template(element_name)
    return {"success": True, **result}


@whatsapp_router.post("/whatsapp/templates/media")
def upload_media(
    file_type: str = Form(...),
    file: Optional[UploadFile] = File(None),
    file_url: Optional[str] = Form(None),
):
    """Upload sample media for a template, returning a handleId to pass as example_media when applying for a template."""
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
