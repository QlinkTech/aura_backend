from fastapi import APIRouter, UploadFile, File, Body
from fastapi.responses import JSONResponse
from app.core.agent import get_embedding
from app.services.db.pinecone_utils import upsert_kb, fetch_kb, chunk_text, fetch_records_with_metadata, delete_record_by_id, list_records_by_label
from app.utils.logger_config import logger
import uuid
import re
import PyPDF2


def clean_pdf_text(text: str) -> str:
    text = re.sub(r'\n +', ' ', text)
    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\n+', '\n', text)
    return text.strip()

kb_router = APIRouter()


@kb_router.post("/kb/upload")
async def upload_kb(file: UploadFile = File(...)):
    try:
        logger.info("KB upload request", extra={"input_file": file.filename, "content_type": file.content_type})
        if file.content_type != "application/pdf":
            return JSONResponse({"error": "Only PDF files allowed"}, status_code=400)

        pdf_reader = PyPDF2.PdfReader(file.file)
        full_text = ""
        for page in pdf_reader.pages:
            full_text += page.extract_text() or ""

        full_text = clean_pdf_text(full_text)

        if not full_text.strip():
            return JSONResponse({"error": "PDF text is empty"}, status_code=400)

        chunks = chunk_text(full_text)
        for chunk in chunks:
            embedding = get_embedding(chunk)
            upsert_kb(vector=embedding, text=chunk, doc_id=str(uuid.uuid4()))

        logger.info("KB upload complete", extra={"input_file": file.filename, "chunks_uploaded": len(chunks)})
        return {"success": True, "chunks_uploaded": len(chunks)}

    except Exception as e:
        raise e


@kb_router.post("/kb/add-text")
async def add_text_to_kb(data: dict = Body(...)):
    text = data.get("text")
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)

    chunks = chunk_text(text)
    for chunk in chunks:
        vector = get_embedding(chunk)
        upsert_kb(vector=vector, text=chunk, doc_id=str(uuid.uuid4()))

    logger.info("KB text added", extra={"chunks_uploaded": len(chunks)})
    return {"success": True, "chunks_uploaded": len(chunks)}


@kb_router.get("/kb/all")
def list_kb_records():
    logger.info("List KB records request")
    return list_records_by_label()


@kb_router.get("/kb/id/{doc_id}")
def get_kb_record(doc_id: str):
    logger.info("Get KB record request", extra={"doc_id": doc_id})
    empty_vector = [0] * 1536
    results = fetch_kb(vector=empty_vector, top_k=1000)
    for r in results:
        if r["id"] == doc_id:
            return r
    return JSONResponse({"error": "record not found"}, status_code=404)


@kb_router.put("/kb/update/{doc_id}")
async def update_kb_record(doc_id: str, data: dict = Body(...)):
    text = data.get("text")
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)

    logger.info("Update KB record request", extra={"doc_id": doc_id})
    delete_record_by_id(doc_id)

    chunks = chunk_text(text)
    for chunk in chunks:
        vector = get_embedding(chunk)
        upsert_kb(vector=vector, text=chunk, doc_id=str(uuid.uuid4()))

    logger.info("KB record updated", extra={"doc_id": doc_id, "new_chunks": len(chunks)})
    return {"success": True}


@kb_router.delete("/kb/delete/{doc_id}")
def remove_kb_record(doc_id: str):
    logger.info("Delete KB record request", extra={"doc_id": doc_id})
    delete_record_by_id(doc_id)
    return {"success": True}


@kb_router.post("/kb/search")
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
