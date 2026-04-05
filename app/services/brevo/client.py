from brevo import Brevo
from brevo.transactional_emails import SendTransacEmailRequestSender, SendTransacEmailRequestToItem
from fastapi import HTTPException, status
from app.utils.env_load import brevo_api_key
from app.utils.logger_config import logger
from app.services.brevo.email_bodies.welcome import get_welcome_email_html
from app.services.brevo.email_bodies.account_created import get_account_created_email_html
from app.services.brevo.email_bodies.reset_password import get_reset_password_email_html
from app.services.brevo.email_bodies.thank_you import get_thank_you_email_html
from app.services.brevo.email_bodies.vision_board_ready import get_vision_board_ready_email_html

SENDER_EMAIL = "noreply@manifestwithaura.com"
SENDER_NAME = "Aura by Sanaya"

LIST_REGISTERED = 2   # users who created an account
LIST_SUBSCRIBED  = 3  # users who paid/subscribed

brevo_client = Brevo(api_key=brevo_api_key)


def add_contact_to_list(email: str, name: str = "", list_id: int = None) -> dict:
    try:
        logger.info("Adding contact to Brevo list", extra={"email": email, "list_id": list_id})
        result = brevo_client.contacts.create_contact(
            email=email,
            attributes={"FIRSTNAME": name} if name else {},
            list_ids=[list_id] if list_id else [],
            update_enabled=True,
        )
        logger.info("Contact added to Brevo list", extra={"email": email, "list_id": list_id})
        return result
    except Exception as e:
        logger.error("Failed to add contact to Brevo list", extra={"email": email, "list_id": list_id, "error": str(e)})
        raise


def add_registered_contact(email: str, name: str = ""):
    return add_contact_to_list(email=email, name=name, list_id=LIST_REGISTERED)


def add_subscribed_contact(email: str, name: str = ""):
    return add_contact_to_list(email=email, name=name, list_id=LIST_SUBSCRIBED)


def send_email(to_email: str, to_name: str, subject: str, html_content: str) -> dict:
    try:
        logger.info("Sending email via Brevo", extra={"to_email": to_email, "subject": subject})
        result = brevo_client.transactional_emails.send_transac_email(
            html_content=html_content,
            sender=SendTransacEmailRequestSender(
                email=SENDER_EMAIL,
                name=SENDER_NAME,
            ),
            subject=subject,
            to=[
                SendTransacEmailRequestToItem(
                    email=to_email,
                    name=to_name,
                )
            ],
        )
        logger.info("Email sent successfully via Brevo", extra={"to_email": to_email, "message_id": getattr(result, "message_id", None)})
        return result
    except Exception as e:
        logger.error("Failed to send email via Brevo", extra={"to_email": to_email, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send email: {str(e)}"
        )


def send_welcome_email(to_email: str, to_name: str = "") -> dict:
    return send_email(
        to_email=to_email,
        to_name=to_name,
        subject="Welcome to the Aura",
        html_content=get_welcome_email_html(name=to_name),
    )


def send_account_created_email(to_email: str, to_name: str = "") -> dict:
    return send_email(
        to_email=to_email,
        to_name=to_name,
        subject="You're in — The Aura",
        html_content=get_account_created_email_html(name=to_name),
    )


def send_thank_you_email(to_email: str, to_name: str = "") -> dict:
    return send_email(
        to_email=to_email,
        to_name=to_name,
        subject="Thank you for subscribing — The Aura",
        html_content=get_thank_you_email_html(name=to_name),
    )


def send_vision_board_ready_email(to_email: str, to_name: str = "") -> dict:
    return send_email(
        to_email=to_email,
        to_name=to_name,
        subject="Your vision board is ready — The Aura",
        html_content=get_vision_board_ready_email_html(name=to_name),
    )


def send_reset_password_email(to_email: str, to_name: str, reset_link: str) -> dict:
    return send_email(
        to_email=to_email,
        to_name=to_name,
        subject="Reset your password — The Aura",
        html_content=get_reset_password_email_html(name=to_name, reset_link=reset_link),
    )
