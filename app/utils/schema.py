from pydantic import BaseModel

class RegisterRequest(BaseModel):
    email: str
    password: str
    user_name: str

class LoginRequest(BaseModel):
    email: str
    password: str

class GenerateVisionRequest(BaseModel):
    answers: dict
    vibe: dict


class ChatModel(BaseModel):
    message: str

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