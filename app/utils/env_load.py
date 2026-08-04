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
razorpay_app_id = os.getenv("RAZORPAY_APP_ID")
razorpay_app_secrete = os.getenv("RAZORPAY_APP_SECRETE")

admin_api_key = os.getenv("ADMIN_API_KEY")

sarvam_api = os.getenv("SARVAM_API")
elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
resend_api_key = os.getenv("RESEND_API_KEY")

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

google_client_id = os.getenv("GOOGLE_CLIENT_ID")
google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

r2_access_key = os.getenv("R2_ACCESS_KEY")
r2_secret_key = os.getenv("R2_SECRET_KEY")
r2_endpoint = os.getenv("R2_ENDPOINT")
r2_bucket = os.getenv("R2_BUCKET")
r2_public_url = os.getenv("R2_PUBLIC_URL")

gupshup_app_id = os.getenv("GUPSHUP_APP_ID")
gupshup_token = os.getenv("GUPSHUP_TOKEN")
gupshup_app_name = os.getenv("GUPSHUP_APP_NAME")

chorma_tenant = os.getenv("CHROMA_TENANT")
chroma_api = os.getenv("CHROMA_API")