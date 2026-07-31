"""
One-time migration: copy user long-term-memory vectors from Pinecone to Chroma.

Moves both Pinecone namespaces into the Chroma `user_ltm` collection (database
`aura`), matching the split used by app/services/db/chroma/utils.py:
  - "sanaya" (user_id, text)            -> metadata.type = "memory"
  - "aura_journal_entry" (email, text)  -> metadata.type = "journal"

Original embeddings are copied as-is (no re-embedding via OpenAI). Storage
follows Chroma's own idiom rather than Pinecone's: text goes in `documents`
only (not duplicated into metadata), and IDs are proper UUIDs rather than
Pinecone's `{user_id}#{random}` convention — the "sanaya" namespace embedded
the user's email in plaintext as the vector ID, which Chroma has no need for
since lookups already go through metadata `where` filters.

  - memory records get a UUID5 derived from the original Pinecone vector ID
    (deterministic, so re-running this script overwrites the same Chroma
    record instead of duplicating it — without leaking the email into the ID).
  - journal records keep their original ID (a Mongo ObjectId string, already
    opaque) since app/routes/user_sub_routes/journal.py deletes by that exact
    id in both Mongo and the vector store.

Run from project root:
    python -m scripts.migrate_ltm_to_chroma [--dry-run] [--batch-size 100]
"""

import argparse
import uuid
from datetime import datetime, timezone

from app.services.db.pinecone_utils import index, pinecone_namespace, pinecone_journal_namespace
from app.services.db.chroma.client import get_user_ltm_collection

# (pinecone_namespace, chroma record type, pinecone metadata field holding the user, keep original id)
NAMESPACES = [
    (pinecone_namespace, "memory", "user_id", False),
    (pinecone_journal_namespace, "journal", "email", True),
]


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _list_all_ids(namespace: str) -> list:
    all_ids = []
    for page in index.list(namespace=namespace):
        all_ids.extend(page)
    return all_ids


def migrate_namespace(namespace: str, record_type: str, user_field: str, keep_id: bool, batch_size: int, dry_run: bool):
    collection = get_user_ltm_collection()

    all_ids = _list_all_ids(namespace)
    print(f"\n[{namespace}] found {len(all_ids)} vector(s){'  [DRY RUN]' if dry_run else ''}")

    migrated = skipped = 0

    for batch_ids in _chunks(all_ids, batch_size):
        fetched = index.fetch(ids=batch_ids, namespace=namespace)

        ids, embeddings, documents, metadatas = [], [], [], []
        for vector_id, vector in fetched.vectors.items():
            metadata = vector.metadata or {}
            user_id = metadata.get(user_field, "")
            text = metadata.get("text", "")

            if not vector.values or not user_id:
                print(f"  SKIP {vector_id} (missing values or {user_field})")
                skipped += 1
                continue

            created_at = metadata.get("created_at") or datetime.now(timezone.utc).isoformat()
            chroma_id = vector_id if keep_id else str(uuid.uuid5(uuid.NAMESPACE_OID, vector_id))

            ids.append(chroma_id)
            embeddings.append(vector.values)
            documents.append(text)
            metadatas.append({
                "user_id": user_id,
                "type": record_type,
                "created_at": created_at,
            })

        if ids and not dry_run:
            collection.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

        migrated += len(ids)
        print(f"  batch of {len(batch_ids)}: migrated={len(ids)} skipped={len(batch_ids) - len(ids)}")

    return migrated, skipped


def migrate(batch_size: int = 100, dry_run: bool = False):
    total_migrated = total_skipped = 0

    for namespace, record_type, user_field, keep_id in NAMESPACES:
        migrated, skipped = migrate_namespace(namespace, record_type, user_field, keep_id, batch_size, dry_run)
        total_migrated += migrated
        total_skipped += skipped

    print(f"\nDone. migrated={total_migrated} skipped={total_skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to Chroma")
    parser.add_argument("--batch-size", type=int, default=100, help="Pinecone fetch / Chroma upsert batch size")
    args = parser.parse_args()
    migrate(batch_size=args.batch_size, dry_run=args.dry_run)
