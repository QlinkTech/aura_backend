import re
import uuid
from datetime import datetime

from openai import OpenAI

from app.services.db.chroma.client import get_kb_collection, get_user_ltm_collection
from app.utils.env_load import openai_api_key
from app.utils.logger_config import logger

openai_client = OpenAI(api_key=openai_api_key)


def get_embedding(text: str):
    response = openai_client.embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )
    return response.data[0].embedding


def get_embeddings(texts: list) -> list:
    """Batch-embed multiple texts in a single OpenAI call."""
    response = openai_client.embeddings.create(
        input=texts,
        model="text-embedding-3-small"
    )
    return [item.embedding for item in response.data]


def _get_collection(collection: str):
    if collection == "user_ltm":
        return get_user_ltm_collection()
    return get_kb_collection()


def _matches_from_query(response: dict) -> list:
    """Flatten a Chroma query() response (single query) into {id, metadata} matches,
    folding the document text back into metadata['text'] for callers."""
    ids = (response.get("ids") or [[]])[0]
    metadatas = (response.get("metadatas") or [[]])[0]
    documents = (response.get("documents") or [[]])[0]
    matches = []
    for record_id, metadata, document in zip(ids, metadatas, documents):
        matches.append({"id": record_id, "metadata": {**(metadata or {}), "text": document}})
    return matches


def upsert_data(
    user_id: str,
    vector: list,
    text: str
) -> None:
    """Chroma util function to append a new user long-term-memory vector."""
    try:
        vector_id = str(uuid.uuid4())
        logger.info("Upserting user memory vector", extra={"user_id": user_id, "vector_id": vector_id})
        collection = get_user_ltm_collection()
        collection.upsert(
            ids=[vector_id],
            embeddings=[vector],
            documents=[text],
            metadatas=[{
                "user_id": user_id,
                "type": "memory",
                "created_at": datetime.now().isoformat()
            }]
        )
        logger.info("User memory vector upserted", extra={"user_id": user_id, "vector_id": vector_id})

    except Exception as e:
        logger.error("Error upserting user memory vector", extra={"user_id": user_id, "error": str(e)})
        raise e


def fetch_data(
    vector: list,
    user_id: str,
    top_k: int = 3
) -> list:
    """Chroma util function to perform similarity search over a user's long-term memory."""
    try:
        logger.info("Fetching user memory vectors", extra={"user_id": user_id, "top_k": top_k})
        collection = get_user_ltm_collection()
        result = collection.query(
            query_embeddings=[vector],
            n_results=top_k,
            where={"$and": [{"user_id": {"$eq": user_id}}, {"type": {"$eq": "memory"}}]},
            include=["metadatas", "documents", "distances"]
        )

        matches = _matches_from_query(result)
        logger.info("User memory vectors fetched", extra={"user_id": user_id, "matches": len(matches)})
        return matches

    except Exception as e:
        logger.error("Error fetching user memory vectors", extra={"user_id": user_id, "error": str(e)})
        raise e


def fetch_kb(
    vector: list,
    top_k: int = 3
) -> list:
    """Chroma util function to perform similarity search over the knowledge base."""
    try:
        collection = get_kb_collection()
        result = collection.query(
            query_embeddings=[vector],
            n_results=top_k,
            include=["metadatas", "documents", "distances"]
        )

        return _matches_from_query(result)

    except Exception as e:
        logger.error("Error fetching KB vectors", extra={"error": str(e)})
        raise e


def upsert_kb(
    vector: list,
    text: str,
    doc_id: str
) -> None:
    """Chroma util function to append/update a knowledge base vector."""
    try:
        logger.info("Upserting KB vector", extra={"doc_id": doc_id})
        collection = get_kb_collection()
        collection.upsert(
            ids=[doc_id],
            embeddings=[vector],
            documents=[text],
            metadatas=[{
                "created_at": datetime.now().isoformat()
            }]
        )
        logger.info("KB vector upserted", extra={"doc_id": doc_id})

    except Exception as e:
        logger.error("Error upserting KB vector", extra={"doc_id": doc_id, "error": str(e)})
        raise e


def upsert_kb_batch(
    ids: list,
    vectors: list,
    texts: list,
    metadatas: list | None = None
) -> None:
    """Batch upsert multiple KB chunks (e.g. all chunks of one document) in a single Chroma call."""
    try:
        logger.info("Batch upserting KB vectors", extra={"count": len(ids)})
        collection = get_kb_collection()
        created_at = datetime.now().isoformat()
        full_metadatas = [
            {"created_at": created_at, **(meta or {})}
            for meta in (metadatas or [{}] * len(ids))
        ]
        collection.upsert(ids=ids, embeddings=vectors, documents=texts, metadatas=full_metadatas)
        logger.info("KB vectors batch upserted", extra={"count": len(ids)})

    except Exception as e:
        logger.error("Error batch upserting KB vectors", extra={"count": len(ids), "error": str(e)})
        raise e


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 200) -> list:
    # Normalize whitespace while preserving paragraph breaks
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)

    # Split on paragraphs first, then sentences — preserves semantic boundaries
    paragraphs = re.split(r'\n\n+', text)
    sentences = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        for s in re.split(r'(?<=[.!?])\s+', para):
            s = s.strip()
            if s:
                sentences.append(s)

    chunks = []
    current = ""

    for sentence in sentences:
        # Hard-split sentences that exceed max_chars on their own
        if len(sentence) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            for i in range(0, len(sentence), max_chars - overlap):
                part = sentence[i:i + max_chars].strip()
                if part:
                    chunks.append(part)
            continue

        if len(current) + 1 + len(sentence) <= max_chars:
            current = (current + " " + sentence).strip() if current else sentence
        else:
            if current:
                chunks.append(current.strip())
            # Seed next chunk with the tail of the previous for context continuity
            overlap_seed = current[-overlap:].strip() if len(current) > overlap else current
            current = (overlap_seed + " " + sentence).strip() if overlap_seed else sentence

    if current:
        chunks.append(current.strip())

    return [c for c in chunks if c]


async def fetch_records_with_metadata(query: str, top_k: int = 3):
    try:
        logger.info("Fetching KB records with metadata", extra={"query": query, "top_k": top_k})
        vector = get_embedding(query)
        results = fetch_kb(vector, top_k)

        kb = []
        for r in results:
            if r.get("metadata"):
                kb.append({
                    "id": r["id"],
                    **r["metadata"]
                })

        return kb

    except Exception as e:
        logger.error("Error fetching KB records with metadata", extra={"query": query, "error": str(e)})
        return []


def upsert_journal(email: str, vector: list, summary: str, log_id: str) -> None:
    """Upsert a journal summary embedding into the user_ltm collection (type=journal)."""
    try:
        logger.info("Upserting journal vector", extra={"email": email, "log_id": log_id})
        collection = get_user_ltm_collection()
        collection.upsert(
            ids=[log_id],
            embeddings=[vector],
            documents=[summary],
            metadatas=[{
                "user_id": email,
                "type": "journal",
                "created_at": datetime.now().isoformat()
            }]
        )
        logger.info("Journal vector upserted", extra={"email": email, "log_id": log_id})
    except Exception as e:
        logger.error("Error upserting journal vector", extra={"email": email, "error": str(e)})
        raise e


def fetch_journal(email: str, vector: list, top_k: int = 5) -> list:
    """Fetch similar journal entries for a user from the user_ltm collection (type=journal)."""
    try:
        logger.info("Fetching journal vectors", extra={"email": email, "top_k": top_k})
        collection = get_user_ltm_collection()
        result = collection.query(
            query_embeddings=[vector],
            n_results=top_k,
            where={"$and": [{"user_id": {"$eq": email}}, {"type": {"$eq": "journal"}}]},
            include=["metadatas", "documents", "distances"]
        )
        matches = _matches_from_query(result)
        logger.info("Journal vectors fetched", extra={"email": email, "matches": len(matches)})
        return matches
    except Exception as e:
        logger.error("Error fetching journal vectors", extra={"email": email, "error": str(e)})
        raise e


def delete_record_by_id(record_id: str, collection: str = "kb") -> None:
    """Delete a record by its ID from the given collection ('kb' or 'user_ltm')."""
    try:
        logger.info("Deleting Chroma record", extra={"record_id": record_id, "collection": collection})
        _get_collection(collection).delete(ids=[record_id])
        logger.info("Chroma record deleted", extra={"record_id": record_id})
    except Exception as e:
        logger.error("Error deleting Chroma record", extra={"record_id": record_id, "error": str(e)})
        raise e


def list_records_by_label(collection: str = "kb", where: dict = None) -> list:
    """Fetch all records in the given collection ('kb' or 'user_ltm'), optionally
    filtered by an exact-match metadata `where` clause (e.g. {"source": {"$eq": "x.pdf"}})."""
    try:
        logger.info("Listing Chroma records", extra={"collection": collection, "where": where})
        kwargs = {"include": ["metadatas", "documents"]}
        if where:
            kwargs["where"] = where
        result = _get_collection(collection).get(**kwargs)
        ids = result.get("ids", [])
        metadatas = result.get("metadatas", [])
        documents = result.get("documents", [])

        output = [
            {"id": record_id, "metadata": {**(metadata or {}), "text": document}}
            for record_id, metadata, document in zip(ids, metadatas, documents)
        ]

        logger.info("Chroma records listed", extra={"collection": collection, "count": len(output)})
        return output
    except Exception as e:
        logger.error("Error listing Chroma records", extra={"collection": collection, "error": str(e)})
        raise e


def list_kb_sources() -> list:
    """Distinct, non-empty 'source' metadata values in the kb collection (filenames /
    doc sources), sorted — the values a file_name filter dropdown should offer."""
    try:
        result = get_kb_collection().get(include=["metadatas"])
        metadatas = result.get("metadatas", [])
        sources = {m.get("source") for m in metadatas if m and m.get("source")}
        return sorted(sources)
    except Exception as e:
        logger.error("Error listing KB sources", extra={"error": str(e)})
        raise e
