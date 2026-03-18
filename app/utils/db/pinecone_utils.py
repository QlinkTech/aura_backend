from pinecone import Pinecone
import random
import string
from datetime import datetime
from app.utils.env_load import pinecone_api
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
    
    except Exception as e:
        raise e
    
def fetch_data(
    vector: list,
    user_id: str,
    top_k: int = 3
) -> list:
    """Pinecone util function to perform similarity search in the db."""
    try:
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

        return result.get("matches", [])
    
    except Exception as e:
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
        raise e
    
def upsert_kb(
    vector: list,
    text: str,
    doc_id: str
) -> None:
    """Pinecone Util Function to append new vector to the db."""
    try:
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
    
    except Exception as e:
        raise e
    

def chunk_text(text, max_chars=1200, overlap=200):
    sentences = re.split(r'(?<=[.!?]) +', text)
    chunks = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) <= max_chars:
            current += sentence + " "
        else:
            chunks.append(current.strip())
            current = sentence + " "

    if current:
        chunks.append(current.strip())
        
    final_chunks = []
    for i in range(len(chunks)):
        start = max(0, i - 1)
        merged = " ".join(chunks[start:i+1])
        final_chunks.append(merged)

    return final_chunks


async def fetch_records_with_metadata(query: str, top_k: int = 3):
    try:
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
        return []
    
def delete_record_by_id(record_id: str, namespace: str = pinecone_kb_namespace):
    """Delete a record from Pinecone namespace by its ID."""
    try:
        index.delete(ids=[record_id], namespace=namespace)
    except Exception as e:
        raise e
    
def list_records_by_label(namespace: str = pinecone_kb_namespace):
    """Fetch all records in the given namespace filtered by label (agent/general)."""
    try:
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
                
        return output if output else []
    except Exception as e:
        raise e