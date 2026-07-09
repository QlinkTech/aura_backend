from typing import Literal, Optional
from pydantic import BaseModel

class RegisterRequest(BaseModel):
    email: str
    password: str
    user_name: str
    phone: str = ""

class LoginRequest(BaseModel):
    email: str
    password: str

class GenerateVisionRequest(BaseModel):
    answers: dict
    vibe: dict


class NewSessionRequest(BaseModel):
    source: str = "direct"

class ChatModel(BaseModel):
    message: str
    session_id: str = None
    source: str = "direct"

class PromptModel(BaseModel):
    prompt: str

class CheckUserRequest(BaseModel):
    email: str

class RequestResetPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class EarlyBirdSubRequest(BaseModel):
    email: str
    plan_key: str
    expire_by: int = None

class SubscribeRequest(BaseModel):
    email: str
    plan_key: str
    expire_by: int = None

class ManageSubscriptionRequest(BaseModel):
    email: str
    cancel_at_cycle_end: bool = False  # only used for cancel

class JournalModel(BaseModel):
    journal_prompt: str = ""
    journal_entry: str


class EFTChatModel(BaseModel):
    message: str
    session_id: str = None

class GuidedVizModel(BaseModel):
    message: str

class GoogleAuthRequest(BaseModel):
    id_token: str

class GoogleCodeAuthRequest(BaseModel):
    code: str
    redirect_uri: str

class ActivateFreePlanRequest(BaseModel):
    email: str

class SendPhoneOtpRequest(BaseModel):
    phone: str

class VerifyPhoneOtpRequest(BaseModel):
    phone: str
    otp: str

class SendNotificationModel(BaseModel):
    target: str          # "all" or a specific email
    type: str            # e.g. "new_masterclass", "system_announcement"
    title: str
    body: str
    data: dict = {}

class CreateWhatsappTemplateModel(BaseModel):
    element_name: str
    category: Literal["AUTHENTICATION", "MARKETING", "UTILITY"]
    template_type: str = "TEXT"
    content: str
    example: str
    vertical: str = "TEXT"
    language_code: str = "en_US"
    header: Optional[str] = None
    footer: Optional[str] = None
    example_header: Optional[str] = None
    example_media: Optional[str] = None
    buttons: Optional[list] = None
    enable_sample: bool = True
    allow_template_category_change: bool = False
    add_security_recommendation: Optional[bool] = None
    code_expiration_minutes: Optional[int] = None
    message_send_ttl_seconds: Optional[int] = None
    is_cpr: Optional[bool] = None
    parameter_format: Optional[Literal["NAMED", "POSITIONAL"]] = None

class TriggerWhatsappCampaignModel(BaseModel):
    name: str
    template_id: str                 # id of an APPROVED template (from Get Templates)
    params: list = []                # values for the template's {{1}}, {{2}}, ... placeholders
    target: Literal["all", "tiers"] = "all"
    tiers: Optional[list] = None     # required when target="tiers": daily/high/medium/low/inactive

class EditWhatsappTemplateModel(BaseModel):
    content: Optional[str] = None
    template_type: Optional[str] = None
    example: Optional[str] = None
    example_header: Optional[str] = None
    enable_sample: Optional[bool] = None
    header: Optional[str] = None
    footer: Optional[str] = None
    buttons: Optional[list] = None
    example_media: Optional[str] = None
    media_id: Optional[str] = None
    media_url: Optional[str] = None
    category: Optional[Literal["AUTHENTICATION", "MARKETING", "UTILITY"]] = None