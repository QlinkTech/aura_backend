from dotenv import load_dotenv
import os

load_dotenv()

mongodb_uri = os.getenv("MONGO_URI")
secret_key = os.getenv("SECRET_KEY")
app_password = os.getenv("APP_PASSWORD")
pinecone_api = os.getenv("PINECONE_API")
openai_api_key = os.getenv("OPENAI_API_KEY")
gemini_api_key = os.getenv("GEMINI_API_KEY")

cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME")
cloud_api_key=os.getenv("CLOUDINARY_API_KEY")
cloud_api_secret=os.getenv("CLOUDINARY_API_SECRET")

username = os.environ.get("LOGIN_USERNAME")
password = os.environ.get("LOGIN_PASS")

razorpay_webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")
razorpay_app_id = os.getenv("TEST_RAZORPAY_APP_ID")
razorpay_app_secrete = os.getenv("TEST_RAZORPAY_APP_SECRETE")

admin_api_key = os.getenv("ADMIN_API_KEY")
