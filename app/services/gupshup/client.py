import json
import requests
from fastapi import HTTPException, status
from app.utils.constants import GUPSHUP_SOURCE
from app.utils.env_load import gupshup_app_id, gupshup_app_name, gupshup_token
from app.utils.logger_config import logger

OTP_TEMPLATE_ID = "5a65995b-bd1b-4cfc-bff7-89f766b9fd8c"  # "otp3" approved authentication template


def send_otp_template(phone_number: str, otp_code: str) -> None:
    """Sends the approved 'otp_fom3' WhatsApp authentication template with the OTP code."""
    if not gupshup_app_id or not gupshup_token or not gupshup_app_name:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="WhatsApp OTP service not configured")

    logger.info("Sending OTP template", extra={"phone_number": phone_number})

    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/template/msg"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "token": gupshup_token,
    }
    data = {
        "source": GUPSHUP_SOURCE,
        "destination": phone_number,
        "src.name": gupshup_app_name,
        "template": json.dumps({
            "id": OTP_TEMPLATE_ID,
            "params": [otp_code, otp_code],
        }),
    }

    response = requests.post(url, headers=headers, data=data, timeout=10)
    if not response.ok:
        logger.error("Gupshup OTP send failed", extra={"phone_number": phone_number, "status": response.status_code, "body": response.text})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to send OTP via WhatsApp")

    logger.info("OTP template sent", extra={"phone_number": phone_number, "response": response.json()})


def create_template(payload) -> dict:
    """Applies for a new WhatsApp message template on the Gupshup Partner API."""
    if not gupshup_app_id or not gupshup_token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="WhatsApp template service not configured")

    logger.info("Creating WhatsApp template", extra={"element_name": payload.element_name, "category": payload.category})

    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/templates"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "token": gupshup_token,
    }

    data = {
        "elementName": payload.element_name,
        "languageCode": payload.language_code,
        "category": payload.category,
        "templateType": payload.template_type,
        "vertical": payload.vertical,
        "content": payload.content,
        "example": payload.example,
        "enableSample": str(payload.enable_sample).lower(),
        "allowTemplateCategoryChange": str(payload.allow_template_category_change).lower(),
    }
    if payload.header is not None:
        data["header"] = payload.header
    if payload.footer is not None:
        data["footer"] = payload.footer
    if payload.example_header is not None:
        data["exampleHeader"] = payload.example_header
    if payload.example_media is not None:
        data["exampleMedia"] = payload.example_media
        data["appId"] = gupshup_app_id
    if payload.buttons is not None:
        data["buttons"] = json.dumps(payload.buttons)
    if payload.add_security_recommendation is not None:
        data["addSecurityRecommendation"] = str(payload.add_security_recommendation).lower()
    if payload.code_expiration_minutes is not None:
        data["codeExpirationMinutes"] = payload.code_expiration_minutes
    if payload.message_send_ttl_seconds is not None:
        data["message_send_ttl_seconds"] = payload.message_send_ttl_seconds
    if payload.is_cpr is not None:
        data["isCPR"] = str(payload.is_cpr).lower()
    if payload.parameter_format is not None:
        data["parameterFormat"] = payload.parameter_format

    response = requests.post(url, headers=headers, data=data, timeout=15)
    if not response.ok:
        logger.error("Gupshup template creation failed", extra={"element_name": payload.element_name, "status": response.status_code, "body": response.text})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to create template: {response.text}")

    result = response.json()
    logger.info("WhatsApp template created", extra={
        "element_name": payload.element_name,
        "template_id": result.get("template", {}).get("id"),
        "status": result.get("template", {}).get("status"),
    })
    return result


def list_templates(params: dict) -> dict:
    """Fetches the list of WhatsApp templates for the configured Gupshup app."""
    if not gupshup_app_id or not gupshup_token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="WhatsApp template service not configured")

    query = {}
    for key, value in params.items():
        if value is None:
            continue
        query[key] = "true" if value is True else "false" if value is False else value

    logger.info("Fetching WhatsApp templates", extra={"params": query})

    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/templates"
    headers = {"token": gupshup_token}

    response = requests.get(url, headers=headers, params=query, timeout=15)
    if not response.ok:
        logger.error("Gupshup template list fetch failed", extra={"status": response.status_code, "body": response.text})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to fetch templates: {response.text}")

    result = response.json()
    logger.info("WhatsApp templates fetched", extra={"count": len(result.get("templates", []))})
    return result


def edit_template(template_id: str, payload) -> dict:
    """Edits an existing WhatsApp template identified by templateId on the Gupshup Partner API."""
    if not gupshup_app_id or not gupshup_token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="WhatsApp template service not configured")

    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/templates/{template_id}"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "token": gupshup_token,
    }

    data = {}
    if payload.content is not None:
        data["content"] = payload.content
    if payload.template_type is not None:
        data["templateType"] = payload.template_type
    if payload.example is not None:
        data["example"] = payload.example
    if payload.example_header is not None:
        data["exampleHeader"] = payload.example_header
    if payload.enable_sample is not None:
        data["enableSample"] = str(payload.enable_sample).lower()
    if payload.header is not None:
        data["header"] = payload.header
    if payload.footer is not None:
        data["footer"] = payload.footer
    if payload.buttons is not None:
        data["buttons"] = json.dumps(payload.buttons)
    if payload.example_media is not None:
        data["exampleMedia"] = payload.example_media
    if payload.media_id is not None:
        data["mediaId"] = payload.media_id
    if payload.media_url is not None:
        data["mediaUrl"] = payload.media_url
    if payload.category is not None:
        data["category"] = payload.category

    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update")

    logger.info("Editing WhatsApp template", extra={"template_id": template_id, "fields": list(data.keys())})

    response = requests.put(url, headers=headers, data=data, timeout=15)
    if not response.ok:
        logger.error("Gupshup template edit failed", extra={"template_id": template_id, "status": response.status_code, "body": response.text})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to edit template: {response.text}")

    result = response.json()
    logger.info("WhatsApp template edited", extra={"template_id": template_id})
    return result


def delete_template(element_name: str) -> dict:
    """Permanently deletes a WhatsApp template identified by elementName. Irreversible."""
    if not gupshup_app_id or not gupshup_token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="WhatsApp template service not configured")

    logger.warning("Deleting WhatsApp template", extra={"element_name": element_name})

    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/template/{element_name}"
    headers = {"token": gupshup_token}

    response = requests.delete(url, headers=headers, timeout=15)
    if not response.ok:
        logger.error("Gupshup template deletion failed", extra={"element_name": element_name, "status": response.status_code, "body": response.text})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to delete template: {response.text}")

    result = response.json()
    logger.info("WhatsApp template deleted", extra={"element_name": element_name})
    return result


def upload_template_media(file_type: str, file_bytes: bytes = None, filename: str = None, content_type: str = None, file_url: str = None) -> dict:
    """Uploads sample media for a template and returns a handleId (for the exampleMedia param)."""
    if not gupshup_app_id or not gupshup_token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="WhatsApp template service not configured")
    if not file_bytes and not file_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Either a file or a file_url must be provided")

    logger.info("Uploading WhatsApp template media", extra={"file_type": file_type, "via_url": bool(file_url)})

    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/upload/media"
    headers = {"token": gupshup_token}

    if file_bytes is not None:
        files = {"file": (filename or "upload", file_bytes, content_type or "application/octet-stream")}
        response = requests.post(url, headers=headers, data={"file_type": file_type}, files=files, timeout=30)
    else:
        response = requests.post(url, headers=headers, data={"file_type": file_type, "file": file_url}, timeout=30)

    if not response.ok:
        logger.error("Gupshup template media upload failed", extra={"status": response.status_code, "body": response.text})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to upload template media: {response.text}")

    result = response.json()
    logger.info("WhatsApp template media uploaded", extra={"file_type": file_type})
    return result
