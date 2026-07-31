"""
List (and optionally delete) a user's stored long-term-memory / journal-summary
records in Chroma's user_ltm collection — for auditing what's actually been
remembered about a user, e.g. checking whether a fabricated detail from a chat
reply got written into memory via update_memory and would otherwise resurface
in future sessions as if it were established fact.

Run from project root:
    python -m scripts.inspect_user_memory user@example.com
    python -m scripts.inspect_user_memory user@example.com --search "drained"
    python -m scripts.inspect_user_memory user@example.com --delete <record_id> [<record_id> ...]
"""

import argparse

from app.services.db.chroma.utils import list_records_by_label, delete_record_by_id


def inspect(email: str, search: str = None):
    records = list_records_by_label(collection="user_ltm", where={"user_id": {"$eq": email}})
    if search:
        needle = search.lower()
        records = [r for r in records if needle in (r["metadata"].get("text") or "").lower()]

    print(f"[{email}] {len(records)} record(s){f' matching {search!r}' if search else ''}\n")

    for r in records:
        metadata = r["metadata"]
        print(f"id: {r['id']}")
        print(f"  type: {metadata.get('type', '?')}   created_at: {metadata.get('created_at', '?')}")
        print(f"  text: {metadata.get('text', '')}")
        print()

    return records


def delete(record_ids: list):
    for record_id in record_ids:
        delete_record_by_id(record_id, collection="user_ltm")
        print(f"deleted: {record_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("email", help="User email to inspect")
    parser.add_argument("--search", help="Only show records whose text contains this (case-insensitive)")
    parser.add_argument("--delete", nargs="+", metavar="RECORD_ID", help="Delete these record IDs from user_ltm")
    args = parser.parse_args()

    if args.delete:
        delete(args.delete)
    else:
        inspect(args.email.lower(), args.search)
