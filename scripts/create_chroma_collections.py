"""
One-time setup: create the Chroma collections used by app/services/db/chroma.

Creates (or verifies) `knowledge_base` and `user_ltm` in the `aura` database,
with no embedding function attached — app.services.db.chroma.utils always
computes embeddings itself and passes them explicitly, so Chroma is never
asked to auto-embed.

Run this before scripts/migrate_ltm_to_chroma.py if the collections don't
exist yet, or if you hit:
    ValueError: An embedding function already exists in the collection
    configuration, and a new one is provided.
(that error means a collection was created earlier with a different/default
embedding function — delete it in the Chroma dashboard and re-run this.)

Run from project root:
    python -m scripts.create_chroma_collections
"""

from app.services.db.chroma.client import (
    get_chroma_client,
    KB_COLLECTION_NAME,
    USER_LTM_COLLECTION_NAME,
)


def create_collections():
    client = get_chroma_client()

    for name in (KB_COLLECTION_NAME, USER_LTM_COLLECTION_NAME):
        collection = client.get_or_create_collection(name=name)
        print(f"OK  {name}  (count={collection.count()})")


if __name__ == "__main__":
    create_collections()
