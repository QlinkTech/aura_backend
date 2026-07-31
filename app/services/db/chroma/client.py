import chromadb

from app.utils.env_load import chorma_tenant, chroma_api

CHROMA_DATABASE = "aura"
KB_COLLECTION_NAME = "knowledge_base"
USER_LTM_COLLECTION_NAME = "user_ltm"


def get_chroma_client() -> chromadb.CloudClient:
    """Create a fresh ChromaDB client — avoids stale-connection issues."""
    return chromadb.CloudClient(
        tenant=chorma_tenant,
        database=CHROMA_DATABASE,
        api_key=chroma_api
    )


def get_kb_collection():
    """
    No embedding_function is attached: app.services.db.chroma.utils always
    computes embeddings itself (OpenAI) and passes them explicitly, so Chroma
    never needs to auto-embed. Attaching one here would conflict with
    whatever function is persisted on the collection config.
    """
    client = get_chroma_client()
    return client.get_or_create_collection(name=KB_COLLECTION_NAME)


def get_user_ltm_collection():
    client = get_chroma_client()
    return client.get_or_create_collection(name=USER_LTM_COLLECTION_NAME)
