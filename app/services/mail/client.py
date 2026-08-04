import resend
from fastapi import HTTPException, status
from app.utils.env_load import resend_api_key
from app.utils.logger_config import logger
from app.services.mail.email_bodies.welcome import get_welcome_email_html
from app.services.mail.email_bodies.account_created import get_account_created_email_html
from app.services.mail.email_bodies.reset_password import get_reset_password_email_html
from app.services.mail.email_bodies.thank_you import get_thank_you_email_html
from app.services.mail.email_bodies.vision_board_ready import get_vision_board_ready_email_html
from app.services.mail.email_bodies.subscription_cancelled import get_subscription_cancelled_email_html
from app.services.mail.email_bodies.trial_ended import get_trial_ended_email_html

SENDER_EMAIL = "noreply@regulatewithaura.com"
SENDER_NAME = "Aura by Sanaya"
SENDER = f"{SENDER_NAME} <{SENDER_EMAIL}>"

# Replies go to a monitored inbox, not the unattended noreply sender.
REPLY_TO_EMAIL = "team@regulatewithaura.com"

resend.api_key = resend_api_key


# --- Contact list management (Brevo) — disabled during the Resend migration. ---
# Resend has no equivalent of these numbered lists, so this segmentation is parked
# rather than ported. Restoring it needs `brevo-python` back in requirements.txt and
# BREVO_API_KEY back in env_load.py; call sites are commented out to match.
#
# from brevo import Brevo
# from brevo.contacts.types import RemoveContactFromListRequestBodyEmails
# from app.utils.env_load import brevo_api_key
#
# LIST_REGISTERED = 2   # users who created an account
# LIST_SUBSCRIBED  = 3  # users who paid/subscribed
# LIST_CANCELLED   = 8  # users who cancelled their subscription
# LIST_HALTED      = 9  # users whose subscription is halted
# LIST_TRIAL       = 10 # users currently within their trial period
#
# brevo_client = Brevo(api_key=brevo_api_key)
#
#
# def add_contact_to_list(email: str, name: str = "", list_id: int = None) -> dict:
#     try:
#         logger.info("Adding contact to Brevo list", extra={"email": email, "list_id": list_id})
#         result = brevo_client.contacts.create_contact(
#             email=email,
#             attributes={"FIRSTNAME": name} if name else {},
#             list_ids=[list_id] if list_id else [],
#             update_enabled=True,
#         )
#         logger.info("Contact added to Brevo list", extra={"email": email, "list_id": list_id})
#         return result
#     except Exception as e:
#         logger.error("Failed to add contact to Brevo list", extra={"email": email, "list_id": list_id, "error": str(e)})
#         raise
#
#
# def remove_contact_from_list(email: str, list_id: int) -> None:
#     try:
#         logger.info("Removing contact from Brevo list", extra={"email": email, "list_id": list_id})
#         brevo_client.contacts.remove_contact_from_list(
#             list_id=list_id,
#             request=RemoveContactFromListRequestBodyEmails(emails=[email]),
#         )
#         logger.info("Contact removed from Brevo list", extra={"email": email, "list_id": list_id})
#     except Exception as e:
#         if "already removed" in str(e) or "does not exist" in str(e):
#             logger.debug("Contact not in list — skipping remove", extra={"email": email, "list_id": list_id})
#         else:
#             logger.error("Failed to remove contact from Brevo list", extra={"email": email, "list_id": list_id, "error": str(e)})
#
#
# def add_registered_contact(email: str, name: str = ""):
#     return add_contact_to_list(email=email, name=name, list_id=LIST_REGISTERED)
#
#
# def add_subscribed_contact(email: str, name: str = ""):
#     return add_contact_to_list(email=email, name=name, list_id=LIST_SUBSCRIBED)
#
#
# def add_cancelled_contact(email: str, name: str = ""):
#     return add_contact_to_list(email=email, name=name, list_id=LIST_CANCELLED)
#
#
# def add_halted_contact(email: str, name: str = ""):
#     return add_contact_to_list(email=email, name=name, list_id=LIST_HALTED)
#
#
# def add_trial_contact(email: str, name: str = ""):
#     return add_contact_to_list(email=email, name=name, list_id=LIST_TRIAL)


def send_email(to_email: str, to_name: str, subject: str, html_content: str) -> dict:
    try:
        logger.info("Sending email via Resend", extra={"to_email": to_email, "subject": subject})
        params: resend.Emails.SendParams = {
            "from": SENDER,
            "to": [to_email],
            "subject": subject,
            "html": html_content,
            "reply_to": REPLY_TO_EMAIL,
        }
        result = resend.Emails.send(params)
        logger.info("Email sent successfully via Resend", extra={"to_email": to_email, "message_id": result.get("id")})
        return result
    except Exception as e:
        logger.error("Failed to send email via Resend", extra={"to_email": to_email, "error": str(e)})
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


def send_subscription_cancelled_email(to_email: str, to_name: str = "") -> dict:
    return send_email(
        to_email=to_email,
        to_name=to_name,
        subject="We're sad to see you go — The Aura",
        html_content=get_subscription_cancelled_email_html(name=to_name),
    )


def send_trial_ended_email(to_email: str, to_name: str = "") -> dict:
    return send_email(
        to_email=to_email,
        to_name=to_name,
        subject="Your free trial has ended — The Aura",
        html_content=get_trial_ended_email_html(name=to_name),
    )


def send_reset_password_email(to_email: str, to_name: str, reset_link: str) -> dict:
    return send_email(
        to_email=to_email,
        to_name=to_name,
        subject="Reset your password — The Aura",
        html_content=get_reset_password_email_html(name=to_name, reset_link=reset_link),
    )
