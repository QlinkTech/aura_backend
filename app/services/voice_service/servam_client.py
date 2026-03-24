from sarvamai import SarvamAI
from app.utils.env_load import sarvam_api

sarvam_client = SarvamAI(
    base_url="https://api.sarvam.ai/",
    api_subscription_key=sarvam_api,
)


