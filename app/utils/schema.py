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

class ReGenerateVisionModel(BaseModel):
    email: str
    answers: dict
    vibe: dict

class ChatModel(BaseModel):
    message: str

class PromptModel(BaseModel):
    prompt: str

class CheckUserRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str
    new_password: str

class EarlyBirdSubRequest(BaseModel):
    email: str
    plan_key: str
    expire_by: int = None

class SubscribeRequest(BaseModel):
    email: str
    plan_key: str
    expire_by: int = None

class JournalModel(BaseModel):
    journal_prompt: str
    journal_entry: str