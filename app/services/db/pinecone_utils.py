from pinecone import Pinecone
import random
import string
from datetime import datetime
from app.utils.env_load import pinecone_api
from app.utils.logger_config import logger
import re

from openai import OpenAI
from app.utils.env_load import openai_api_key

pine_client = Pinecone(
    api_key=pinecone_api
)
openai_client = OpenAI(
    api_key=openai_api_key
)

index = pine_client.Index(
    "demo"
)



def get_embedding(text:str):
    response = openai_client.embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )

    return response.data[0].embedding

pinecone_namespace = "sanaya"
pinecone_kb_namespace = "sanaya_kb"
pinecone_kb_test_namespace = "sanaya_kb_test"
pinecone_journal_namespace = "aura_journal_entry"

def _generate_id(length=7):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

def upsert_data(
    user_id: str,
    vector: list,
    text: str
) -> None:
    """Pinecone Util Function to append new vector to the db."""
    try:
        vector_id = f"{user_id}#{_generate_id()}"
        logger.info("Upserting user memory vector", extra={"user_id": user_id, "vector_id": vector_id})
        index.upsert(
            namespace=pinecone_namespace,
            vectors=[
                {
                    "id": vector_id,
                    "values": vector,
                    "metadata": {
                        "user_id": user_id,
                        "text": text,
                        "created_at": datetime.now().isoformat()
                    }
                }
            ]
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
    """Pinecone util function to perform similarity search in the db."""
    try:
        logger.info("Fetching user memory vectors", extra={"user_id": user_id, "top_k": top_k})
        metadata_filter = {
            "user_id": user_id
        }

        result = index.query(
            namespace=pinecone_namespace,
            vector=vector,
            filter=metadata_filter,
            top_k=top_k,
            include_metadata=True
        )

        matches = result.get("matches", [])
        logger.info("User memory vectors fetched", extra={"user_id": user_id, "matches": len(matches)})
        return matches

    except Exception as e:
        logger.error("Error fetching user memory vectors", extra={"user_id": user_id, "error": str(e)})
        raise e

def fetch_kb(
    vector: list,
    top_k: int = 3
) -> list:
    """Pinecone util function to perform similarity search in the db."""
    try:
        result = index.query(
            namespace=pinecone_kb_namespace,
            vector=vector,
            top_k=top_k,
            include_metadata=True
        )

        return result.get("matches", [])

    except Exception as e:
        logger.error("Error fetching KB vectors", extra={"error": str(e)})
        raise e

def upsert_kb(
    vector: list,
    text: str,
    doc_id: str
) -> None:
    """Pinecone Util Function to append new vector to the db."""
    try:
        logger.info("Upserting KB vector", extra={"doc_id": doc_id})
        index.upsert(
            namespace=pinecone_kb_namespace,
            vectors=[
                {
                    "id": doc_id,
                    "values": vector,
                    "metadata": {
                        "text": text,
                        "created_at": datetime.now().isoformat()
                    }
                }
            ]
        )
        logger.info("KB vector upserted", extra={"doc_id": doc_id})

    except Exception as e:
        logger.error("Error upserting KB vector", extra={"doc_id": doc_id, "error": str(e)})
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
            if "metadata" in r:
                kb.append({
                    "id": r["id"],
                    **r["metadata"]
                })

        return kb

    except Exception as e:
        logger.error("Error fetching KB records with metadata", extra={"query": query, "error": str(e)})
        return []

def upsert_journal(email: str, vector: list, summary: str, log_id: str) -> None:
    """Upsert journal summary embedding into the aura_journal_entry namespace."""
    try:
        logger.info("Upserting journal vector", extra={"email": email, "log_id": log_id})
        index.upsert(
            namespace=pinecone_journal_namespace,
            vectors=[
                {
                    "id": log_id,
                    "values": vector,
                    "metadata": {
                        "email": email,
                        "text": summary,
                        "created_at": datetime.now().isoformat()
                    }
                }
            ]
        )
        logger.info("Journal vector upserted", extra={"email": email, "log_id": log_id})
    except Exception as e:
        logger.error("Error upserting journal vector", extra={"email": email, "error": str(e)})
        raise e


def fetch_journal(email: str, vector: list, top_k: int = 5) -> list:
    """Fetch similar journal entries for a user from the aura_journal_entry namespace."""
    try:
        logger.info("Fetching journal vectors", extra={"email": email, "top_k": top_k})
        result = index.query(
            namespace=pinecone_journal_namespace,
            vector=vector,
            filter={"email": email},
            top_k=top_k,
            include_metadata=True
        )
        matches = result.get("matches", [])
        logger.info("Journal vectors fetched", extra={"email": email, "matches": len(matches)})
        return matches
    except Exception as e:
        logger.error("Error fetching journal vectors", extra={"email": email, "error": str(e)})
        raise e


def delete_record_by_id(record_id: str, namespace: str = pinecone_kb_namespace):
    """Delete a record from Pinecone namespace by its ID."""
    try:
        logger.info("Deleting Pinecone record", extra={"record_id": record_id, "namespace": namespace})
        index.delete(ids=[record_id], namespace=namespace)
        logger.info("Pinecone record deleted", extra={"record_id": record_id})
    except Exception as e:
        logger.error("Error deleting Pinecone record", extra={"record_id": record_id, "error": str(e)})
        raise e

def list_records_by_label(namespace: str = pinecone_kb_namespace):
    """Fetch all records in the given namespace filtered by label (agent/general)."""
    try:
        logger.info("Listing Pinecone KB records", extra={"namespace": namespace})
        output = []
        meta_response = None
        response = list(index.list(namespace=namespace))
        if response:
            m_respose = index.fetch(
                ids=response[0],
                namespace=namespace
            )

            vectors = m_respose.vectors

            meta_response = list( {
                "id": vid,
                "metadata": vec.metadata
            }
            for vid, vec in vectors.items())

            output = []
            for mr in meta_response:
                output.append(mr)

        logger.info("KB records listed", extra={"namespace": namespace, "count": len(output)})
        return output if output else []
    except Exception as e:
        logger.error("Error listing KB records", extra={"namespace": namespace, "error": str(e)})
        raise e
