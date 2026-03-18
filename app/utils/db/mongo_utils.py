from datetime import datetime
from fastapi import HTTPException, status
from pymongo import MongoClient
from app.utils.env_load import mongodb_uri
from app.services.auth_service import hash_password, verify_password, create_access_token

mongo_client = MongoClient(mongodb_uri)
db = mongo_client["mmd"]
user_profile = db["user_profile"]
system = db["systems"]
payments = db["payments"]

def create_account(email: str, password: str):
    try:
        email = email.lower()
        existing = user_profile.find_one({"email": email})
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

        hashed_pw = hash_password(password)
        user_profile.insert_one({
            "email": email,
            "password": hashed_pw,
            "chat_history": [],
            "vision_board_url": "",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })
        token = create_access_token({"sub": email, "email": email})
        return {"message": "Account created successfully", "access_token": token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

def login(email: str, password: str):
    try:
        email = email.lower()
        user = user_profile.find_one({"email": email})
        if not user or not verify_password(password, user["password"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        token = create_access_token({"sub": email, "email": email})
        return {"access_token": token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# ---------------- Chat History Utilities ---------------- #

def get_last_chat_history(email: str, limit: int = 10):
    try:
        user = user_profile.find_one({"email": email}, {"chat_history": 1})
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user.get("chat_history", [])[-limit:]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
def get_chat_history(email: str):
    try:
        user = user_profile.find_one({"email": email}, {"chat_history": 1})
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user.get("chat_history", [])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

def add_chat_history(email: str, role: str, content: str):
    try:
        chat_item = {
            "content": content,
            "role": role
        }
        result = user_profile.update_one(
            {"email": email},
            {"$push": {"chat_history": chat_item}, "$set": {"updated_at": datetime.utcnow()}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return {"message": "Chat added successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
def update_vision_board(email: str, url: str):
    try:
        result = user_profile.update_one(
            {"email": email},
            {"$set": {"vision_board_url": url, "updated_at": datetime.utcnow()}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return {"message": "Vision board updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
def get_user_details(email: str):
    try:
        user = user_profile.find_one({"email": email}, {"_id": 0, "chat_history": 0})
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return  user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
    
def check_user_exists(email: str):
    try:
        email = email.lower()
        user = user_profile.find_one({"email": email}, {"_id": 1})
        return {"exists": user is not None}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

def reset_password(email: str, new_password: str):
    try:
        email = email.lower()
        user = user_profile.find_one({"email": email}, {"_id": 1})
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        hashed_pw = hash_password(new_password)
        user_profile.update_one(
            {"email": email},
            {"$set": {"password": hashed_pw, "updated_at": datetime.utcnow()}}
        )
        return {"message": "Password reset successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

def return_system_prompt():
    """Returns system prompt."""
    try:
        response = system.find_one({"category": "system_prompt"}, {"_id": 0})
        return response if response else None
    except Exception as e:
        raise e
    
def update_system_prompt(prompt: str):
    try:
        # Get current doc first
        doc = system.find_one({"category": "system_prompt"})
        if not doc:
            return False

        previous_prompt = doc.get("prompt", "")

        update_fields = {
            "prompt": prompt,
            "old_prompt": previous_prompt
        }

        result = system.update_one(
            {"category": "system_prompt"},
            {"$set": update_fields},
            upsert=False
        )

        return result.modified_count > 0

    except Exception as e:
        raise e

