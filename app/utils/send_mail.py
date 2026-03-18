import smtplib
from email.message import EmailMessage
from app.utils.env_load import app_password

SENDER_EMAIL = "manifestmydreams24@gmail.com"    
GMAIL_PASSWORD = app_password

def send_mail_gmail(msg: EmailMessage, to: str, gmail_user: str, gmail_password: str):
    """Function to send a mail using Gmail SMTP."""
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_password)
            server.send_message(msg)

        print(f"Email sent successfully to {to}")

    except Exception as e:
        print(f"Error sending email to {to}: {e}")
        raise e
    

def send_vision_board_ready_email(to: str, dashboard_link: str):
    """Function to send a notification mail when AI generates the vision board image."""
    subject = "Your vision board is ready! 🌟"

    plain_text_body = f"""
    Hey there 👋,

    Your vision board has been created successfully! ✨  

    Take a moment to soak it in — it's all about your dreams, energy, and the future you're manifesting.  

    You can view it anytime on your dashboard here:
    {dashboard_link}

    — Team Manifest My Dreams
    """

    msg = EmailMessage()
    msg["From"] = SENDER_EMAIL
    msg["To"] = to
    msg["Subject"] = subject
    msg["Reply-To"] = SENDER_EMAIL

    msg.set_content(plain_text_body)

    send_mail_gmail(msg, to, SENDER_EMAIL, GMAIL_PASSWORD)
