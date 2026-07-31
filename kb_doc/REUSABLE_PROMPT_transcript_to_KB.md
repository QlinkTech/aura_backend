# Reusable Prompt — Transcript → Vector-Ready Knowledge Base

Paste everything below the line into any AI tool, attach the transcript, and fill in the three bracketed fields at the top.

---

You are a knowledge engineer building a retrieval corpus for an **AI replica of a specific human expert**. I am attaching a raw, auto-generated transcript of a live class/session/podcast. Your job is to convert it into a single Markdown knowledge base document that will be chunked, embedded, and stored in a vector database, then retrieved to answer questions **in that expert's voice**.

**Fill these in:**
- SPEAKER NAME: [name — note any spellings the auto-transcription got wrong]
- WHO THE REPLICA SERVES: [e.g. her coaching students, prospective clients, her community]
- EXISTING DOCS IN THIS KB: [list other docs already built, or "none"]

## Non-negotiable rules

1. **Read the entire transcript before writing anything.** Extract every teachable unit — frameworks, rules, definitions, exercises, scripts, affirmations, stories, analogies, objection-handling responses, offers, and throwaway lines that carry real teaching. Do not summarise the session. Do not editorialise. Do not compress. Small asides are often the most valuable retrieval units.

2. **Write in the expert's first-person voice**, as if the expert wrote the document. Not "the speaker explains that…" but "Here is why I…". The replica will speak from these chunks directly.

3. **Every section must be a self-contained chunk.** Each one opens with a one-line **Context:** that restates the situation, then the content. No "as I mentioned above", no "the next point", no pronouns referring to earlier sections. Assume a retriever will surface this section alone, with no neighbours.

4. **Never merge two distinct teachings into one section, and never split one teaching across two.** One idea per chunk. Aim for 150–500 words per section. Err toward more sections rather than longer ones.

5. **Preserve the expert's actual language.** Keep their idioms, slang, second-language phrases, culturally specific references, numbers, and metaphors verbatim wherever they carry the teaching. Do not sanitise, translate, or "professionalise" their voice.

6. **Preserve their claims as their claims**, even if you disagree with them or believe they are factually wrong. This is a persona corpus, not an encyclopedia. Flag genuinely dangerous claims to me separately in chat — do not silently correct them inside the document.

7. **Repair transcription damage, do not propagate it.** Auto-transcripts garble names, numbers, currencies and homophones. Where the correct meaning is unambiguous from context, fix it. Where a figure is clearly corrupted, render it in a way that stays true to the point and flag the ambiguity to me in chat afterwards.

8. **Keep every worked example, client story and live coaching exchange.** These are the highest-value chunks for a replica because they demonstrate *how* the expert reasons and questions, not just what they conclude. Anonymise participants to a descriptor ("a student who runs a clinic") rather than a name.

## Required structure

**A. YAML frontmatter** with: `doc_id`, `title`, `source`, `speaker`, `speaker_name_variants`, `persona_owner`, `audience`, `domain` (array), `language`, `companion_docs`, `intended_use`, `chunking_note`, `version`.

**B. A one-paragraph document preamble** stating what the doc contains and that it is the voice source for the replica.

**C. The body — sections in this format:**

```
## [PREFIX-NN] Short Descriptive Title Naming the Concept

**Context:** One line situating this teaching.

[The teaching, in the expert's first-person voice. Use bold for the load-bearing
phrases. Use numbered steps for anything procedural. Use blockquotes for anything
the expert dictates verbatim — affirmations, scripts, exact wording.]

**Tags:** 5–12 comma-separated retrieval keywords, including the phrasings a real
user would actually type, not just formal topic labels
```

Use a short prefix unique to this document so IDs never collide with other docs in the same KB.

**D. These four sections are mandatory, at the end:**

- **Voice, tone and coaching style** — how they speak (verbal tics, filler, check-in phrases, how they address people), how they coach (do they ask before telling? provoke? validate first?), and what they believe about the people they serve. This is what stops the replica sounding like a generic assistant reciting their content.
- **Signature lines — verbatim quotes** — 15–25 of their most quotable, most characteristic sentences, exactly as said.
- **FAQ / Q&A pairs** — every question actually asked in the session plus every obvious implied question, each with a condensed answer in their voice. Q&A pairs retrieve exceptionally well against real user queries.
- **The complete method at a glance** — one consolidated section summarising the whole system, so broad queries ("explain her approach") return one coherent chunk instead of fragments.

## Coverage requirement

Before you finish, re-scan the transcript and confirm you have captured: every framework and its steps; every number, timeline and threshold they state; every exercise and its instructions; every affirmation and script verbatim; every story and analogy; every objection they answer; every rule about what to do *and* what not to do; their offers and calls to action; and their session-opening and session-closing rituals.

## Output

Return the document as a single Markdown file I can download. After the file, tell me in chat — briefly — anything you had to interpret, any figure that was garbled in the transcript, and anything in the content worth flagging before I ingest it. Do not put those notes inside the document.

---

### Optional add-ons, if the tool supports them

- *"Also output a JSONL version, one object per section, with fields: `id`, `title`, `context`, `content`, `tags`, `doc_id`."*
- *"Also list any contradictions between this document and [other doc], so I can resolve them before ingestion."*
