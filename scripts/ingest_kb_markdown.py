"""
Chunk a structured KB markdown doc by its own "## [PREFIX-NN] Title" sections
and upsert each section as one Chroma record (knowledge_base collection).

Built for the kb_doc/*.md format produced by
kb_doc/REUSABLE_PROMPT_transcript_to_KB.md: YAML frontmatter + a body made of
self-contained "## [PREFIX-NN] Title" sections, each with its own
**Context:** / content / **Tags:** — exactly the doc's own chunking_note:
"chunk by H2 section... do not split a section mid-way if avoidable."

This intentionally does NOT use the generic sentence-based chunk_text() in
app/services/db/chroma/utils.py (that one is for raw PDF/text uploads via the
/kb/upload route) — chunk_text() knows nothing about these section boundaries
and would cut a teaching in half at the 1200-char mark.

Chunk IDs are deterministic ("{doc_id}__{section_id}"), so re-running this
script on an edited doc overwrites the same Chroma records instead of
duplicating them.

Run from project root:
    python -m scripts.ingest_kb_markdown kb_doc/KB_Manifestation_Journaling_Masterclass.md
    python -m scripts.ingest_kb_markdown kb_doc/*.md --dry-run
"""

import argparse
import re
from pathlib import Path

import yaml

from app.services.db.chroma.utils import upsert_kb_batch, get_embeddings

SECTION_RE = re.compile(r'^##\s+\[([A-Za-z0-9_-]+)\]\s+(.+?)\s*$', re.MULTILINE)
TAGS_RE = re.compile(r'\*\*Tags:\*\*\s*(.+)', re.IGNORECASE)
EMBED_BATCH_SIZE = 50


def parse_doc(path: Path) -> tuple:
    """Split a kb_doc markdown file into (frontmatter dict, body)."""
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        raise ValueError(f"{path}: missing YAML frontmatter")

    _, frontmatter_raw, body = raw.split("---", 2)
    frontmatter = yaml.safe_load(frontmatter_raw) or {}
    return frontmatter, body


def split_sections(body: str) -> list:
    """Split the body into self-contained '## [PREFIX-NN] Title' sections."""
    matches = list(SECTION_RE.finditer(body))
    sections = []
    for i, m in enumerate(matches):
        section_id, title = m.group(1), m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[start:end].strip()
        content = re.sub(r'\n-{3,}\s*$', '', content).strip()  # trailing '---' rule

        tags_match = TAGS_RE.search(content)
        tags = tags_match.group(1).strip() if tags_match else ""

        sections.append({
            "section_id": section_id,
            "title": title,
            "content": content,
            "tags": tags,
        })
    return sections


def ingest_file(path: Path, batch_size: int, dry_run: bool) -> int:
    frontmatter, body = parse_doc(path)
    doc_id = frontmatter.get("doc_id", path.stem)
    doc_title = frontmatter.get("title", path.stem)
    source = frontmatter.get("source", "")
    speaker = frontmatter.get("speaker", "")
    domain = frontmatter.get("domain", [])
    domain_str = ", ".join(domain) if isinstance(domain, list) else str(domain)
    version = str(frontmatter.get("version", ""))

    sections = split_sections(body)
    print(f"\n[{path.name}] doc_id={doc_id}  sections={len(sections)}{'  [DRY RUN]' if dry_run else ''}")

    if not sections:
        print("  no '## [PREFIX-NN]' sections found — skipping")
        return 0

    ingested = 0
    for batch_start in range(0, len(sections), batch_size):
        batch = sections[batch_start:batch_start + batch_size]
        texts = [s["content"] for s in batch]
        ids = [f"{doc_id}__{s['section_id']}" for s in batch]
        metadatas = [
            {
                "doc_id": doc_id,
                "doc_title": doc_title,
                "section_id": s["section_id"],
                "section_title": s["title"],
                "source": source,
                "speaker": speaker,
                "domain": domain_str,
                "tags": s["tags"],
                "version": version,
            }
            for s in batch
        ]

        for s in batch:
            print(f"  {doc_id}__{s['section_id']}  {s['title']}")

        if not dry_run:
            embeddings = get_embeddings(texts)
            upsert_kb_batch(ids=ids, vectors=embeddings, texts=texts, metadatas=metadatas)

        ingested += len(batch)

    return ingested


def main(paths: list, batch_size: int, dry_run: bool):
    total = 0
    for p in paths:
        total += ingest_file(Path(p), batch_size, dry_run)
    print(f"\nDone. ingested={total}{'  [DRY RUN, nothing written]' if dry_run else ''}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="Path(s) to kb_doc markdown file(s)")
    parser.add_argument("--dry-run", action="store_true", help="Preview chunks without embedding or writing to Chroma")
    parser.add_argument("--batch-size", type=int, default=EMBED_BATCH_SIZE, help="Embedding/upsert batch size")
    args = parser.parse_args()
    main(args.paths, batch_size=args.batch_size, dry_run=args.dry_run)
