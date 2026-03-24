from fastapi import APIRouter, UploadFile, File, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from app.utils.schema import PromptModel
from app.services.db.mongo_utils import return_system_prompt, update_system_prompt
from app.core.agent import get_embedding
from app.services.db.pinecone_utils import upsert_kb, fetch_kb,chunk_text, fetch_records_with_metadata, delete_record_by_id, list_records_by_label
from app.utils.logger_config import logger
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
            logger.warning("Dashboard login attempt with missing credentials")
            return JSONResponse({"success":False, "message": "Invalid Request"}, status_code=401)
        elif (
            username != us or password != pwd
        ):
            logger.warning("Dashboard login failed - invalid credentials", extra={"username": username})
            return JSONResponse({"success":False, "message": "Invalid Username or Password"}, status_code=402)
        else:
            logger.info("Dashboard login successful", extra={"username": username})
            return JSONResponse({"success":True}, status_code=201)
    except Exception as e:
        logger.error("Dashboard login error", extra={"username": username, "error": str(e)})
        return JSONResponse({
            "success": False, "message": str(e)
        }, status_code=501)

@system_router.get("/prompt")
def get_prompt():
    try:
        logger.info("Get system prompt request")
        response = return_system_prompt()
        if not response:
            return JSONResponse({"error": "System prompt not found"}, status_code=404)
        return response
    except Exception as e:
        raise e


@system_router.put("/prompt")
def update_prompt(data: PromptModel):
    try:
        logger.info("Update system prompt request")
        response = update_system_prompt(prompt=data.prompt)
        if response:
            logger.info("System prompt updated successfully")
            return JSONResponse({"success": True}, status_code=200)
        else:
            logger.warning("System prompt update returned no modified count")
            return JSONResponse({"success": False}, status_code=500)
    except Exception as e:
        raise e


@system_router.post("/kb/upload")
async def upload_kb(file: UploadFile = File(...)):
    try:
        logger.info("KB upload request", extra={"filename": file.filename, "content_type": file.content_type})
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

        logger.info("KB upload complete", extra={"filename": file.filename, "chunks_uploaded": len(chunks)})
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

    logger.info("KB text added", extra={"chunks_uploaded": len(chunks)})
    return {"success": True, "chunks_uploaded": len(chunks)}

@system_router.get("/kb/all")
def list_kb_records():
    logger.info("List KB records request")
    docs = list_records_by_label()
    return docs


@system_router.get("/kb/id/{doc_id}")
def get_kb_record(doc_id: str):
    logger.info("Get KB record request", extra={"doc_id": doc_id})
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

    logger.info("Update KB record request", extra={"doc_id": doc_id})
    delete_record_by_id(doc_id)

    chunks = chunk_text(text)
    for chunk in chunks:
        vector = get_embedding(chunk)
        upsert_kb(
            vector=vector,
            text=chunk,
            doc_id=str(uuid.uuid4())
        )

    logger.info("KB record updated", extra={"doc_id": doc_id, "new_chunks": len(chunks)})
    return {"success": True}


@system_router.delete("/kb/delete/{doc_id}")
def remove_kb_record(doc_id: str):
    logger.info("Delete KB record request", extra={"doc_id": doc_id})
    delete_record_by_id(doc_id)
    return {"success": True}

@system_router.post("/kb/search")
async def search_records(data: dict = Body(...)):
    try:
        query = data.get("query")
        logger.info("KB search request", extra={"query": query})
        response = await fetch_records_with_metadata(query=query, top_k=15)
        if not response:
            return JSONResponse({"error": "record not found"}, status_code=404)
        return response
    except Exception as e:
        logger.error("KB search error", extra={"error": str(e)})
        return JSONResponse({"error": "Failed to get records"}, status_code=500)
