from fastapi import APIRouter, UploadFile, File, Body, Query
from fastapi.responses import JSONResponse
from typing import Optional
from app.core.agent import get_embeddings
from app.services.db.chroma.utils import upsert_kb_batch, fetch_kb, chunk_text, fetch_records_with_metadata, delete_record_by_id, list_records_by_label, list_kb_sources
from app.utils.logger_config import logger
import uuid
import re
import PyPDF2

EMBED_BATCH_SIZE = 100


def clean_pdf_text(text: str) -> str:
    text = re.sub(r'\n +', ' ', text)
    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\n+', '\n', text)
    return text.strip()


def upload_chunks(chunks: list, source: str) -> None:
    """Embed and upsert chunks in batches, tagging each with shared document metadata
    (document_id/chunk_index/total_chunks/source) so chunks from one upload stay traceable."""
    document_id = str(uuid.uuid4())
    total_chunks = len(chunks)

    for batch_start in range(0, total_chunks, EMBED_BATCH_SIZE):
        batch = chunks[batch_start:batch_start + EMBED_BATCH_SIZE]
        embeddings = get_embeddings(batch)
        ids = [str(uuid.uuid4()) for _ in batch]
        metadatas = [
            {
                "source": source,
                "document_id": document_id,
                "chunk_index": batch_start + i,
                "total_chunks": total_chunks,
            }
            for i in range(len(batch))
        ]
        upsert_kb_batch(ids=ids, vectors=embeddings, texts=batch, metadatas=metadatas)


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
        upload_chunks(chunks, source=file.filename)

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
    upload_chunks(chunks, source="manual-entry")

    logger.info("KB text added", extra={"chunks_uploaded": len(chunks)})
    return {"success": True, "chunks_uploaded": len(chunks)}


@kb_router.get("/kb/all")
def list_kb_records(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    search: Optional[str] = Query(None, description="Case-insensitive search across title, content, and tags"),
    file_name: Optional[str] = Query(None, description="Filter to chunks from one source file — see GET /kb/file-names for valid values"),
):
    logger.info("List KB records request", extra={"page": page, "limit": limit, "search": search, "file_name": file_name})

    where = {"source": {"$eq": file_name}} if file_name else None
    records = list_records_by_label(where=where)

    results = []
    for r in records:
        metadata = r.get("metadata", {})
        title = metadata.get("section_title") or metadata.get("doc_title") or metadata.get("source") or "Untitled"
        results.append({
            "id": r["id"],
            "title": title,
            "content": metadata.get("text", ""),
            "tags": metadata.get("tags", ""),
            "source": metadata.get("source", ""),
            "doc_title": metadata.get("doc_title"),
            "created_at": metadata.get("created_at"),
        })

    if search:
        needle = search.lower()
        results = [
            r for r in results
            if needle in r["title"].lower() or needle in r["content"].lower() or needle in (r["tags"] or "").lower()
        ]

    total = len(results)
    skip = (page - 1) * limit
    page_results = results[skip: skip + limit]

    return {
        "records": page_results,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if total else 0,
    }


@kb_router.get("/kb/file-names")
def list_kb_file_names():
    """Distinct source file names in the KB — populates the file_name filter dropdown."""
    logger.info("List KB file names request")
    return {"file_names": list_kb_sources()}


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
    upload_chunks(chunks, source="manual-edit")

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
