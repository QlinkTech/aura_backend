from fastapi import APIRouter, UploadFile, File, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from app.utils.schema import PromptModel
from app.utils.db.mongo_utils import return_system_prompt, update_system_prompt
from app.core.agent import get_embedding
from app.utils.db.pinecone_utils import upsert_kb, fetch_kb,chunk_text, fetch_records_with_metadata, delete_record_by_id, list_records_by_label
from datetime import datetime
import uuid
import PyPDF2
from app.utils.env_load import username as us, password as pwd

system_router = APIRouter()

class LoginData(BaseModel):
    username: str
    password: str

@system_router.post("/login")
def login(data: LoginData):
    """Dashboard Login."""
    username = data.username.lower()
    password = data.password
    try:
        if not password or not username:
            return JSONResponse({"success":False, "message": "Invalid Request"}, status_code=401)
        elif (
            username != us or password != pwd
        ):
            return JSONResponse({"success":False, "message": "Invalid Username or Password"}, status_code=402)
        else:
            return JSONResponse({"success":True}, status_code=201)
    except Exception as e:
        return JSONResponse({
            "success": False, "message": str(e)
        }, status_code=501)

@system_router.get("/prompt")
def get_prompt():
    try:
        response = return_system_prompt()
        if not response:
            return JSONResponse({"error": "System prompt not found"}, status_code=404)
        return response
    except Exception as e:
        raise e


@system_router.put("/prompt")
def update_prompt(data: PromptModel):
    try:
        response = update_system_prompt(prompt=data.prompt)
        if response:
            return JSONResponse({"success": True}, status_code=200)
        else:
            return JSONResponse({"success": False}, status_code=500)
    except Exception as e:
        raise e


@system_router.post("/kb/upload")
async def upload_kb(file: UploadFile = File(...)):
    try:
        if file.content_type != "application/pdf":
            return JSONResponse({"error": "Only PDF files allowed"}, status_code=400)

        pdf_reader = PyPDF2.PdfReader(file.file)
        full_text = ""

        for page in pdf_reader.pages:
            full_text += page.extract_text() or ""

        if not full_text.strip():
            return JSONResponse({"error": "PDF text is empty"}, status_code=400)

        # Simple chunking (you can refine)
        chunks = chunk_text(full_text)

        for chunk in chunks:
            embedding = get_embedding(chunk)
            upsert_kb(
                vector=embedding,
                text=chunk,
                doc_id=str(uuid.uuid4())
            )

        return {"success": True, "chunks_uploaded": len(chunks)}
    
    except Exception as e:
        raise e


@system_router.post("/kb/add-text")
async def add_text_to_kb(data: dict = Body(...)):
    text = data.get("text")
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)

    chunks = chunk_text(text)

    for chunk in chunks:
        vector = get_embedding(chunk)
        upsert_kb(
            vector=vector,
            text=chunk,
            doc_id=str(uuid.uuid4())
        )

    return {"success": True, "chunks_uploaded": len(chunks)}

@system_router.get("/kb/all")
def list_kb_records():
    docs = list_records_by_label()
    return docs


@system_router.get("/kb/id/{doc_id}")
def get_kb_record(doc_id: str):
    empty_vector = [0] * 1536
    results = fetch_kb(vector=empty_vector, top_k=1000)

    for r in results:
        if r["id"] == doc_id:
            return r
    return JSONResponse({"error": "record not found"}, status_code=404)


@system_router.put("/kb/update/{doc_id}")
async def update_kb_record(doc_id: str, data: dict = Body(...)):
    text = data.get("text")
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)

    delete_record_by_id(doc_id)

    chunks = chunk_text(text)
    for chunk in chunks:
        vector = get_embedding(chunk)
        upsert_kb(
            vector=vector,
            text=chunk,
            doc_id=str(uuid.uuid4())
        )

    return {"success": True}


@system_router.delete("/kb/delete/{doc_id}")
def remove_kb_record(doc_id: str):
    delete_record_by_id(doc_id)
    return {"success": True}

@system_router.post("/kb/search")
async def search_records(data: dict = Body(...)):
    try:
        query = data.get("query")
        response = await fetch_records_with_metadata(query=query, top_k=15)
        if not response:
            return JSONResponse({"error": "record not found"}, status_code=404)
        return response
    except Exception as e:
        return JSONResponse({"error": "Failed to get records"}, status_code=500)
    
