from pydantic import BaseModel

class RegisterRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class GenerateVisionModel(BaseModel):
    email: str
    name: str
    answers: dict
    vibe: dict
    password: str

class ReGenerateVisionModel(BaseModel):
    email: str
    answers: dict
    vibe: dict

class ChatModel(BaseModel):
    email: str
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