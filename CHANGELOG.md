# Changelog

---

## [2026-03-27] — Pratham Paleriya

### Added
- **Journal feature** — agent extracts `summary`, `mood`, `mood_score`, `people`, `theme` from entries; stores in MongoDB (`journal_log`) and Pinecone (`aura_journal_entry`)
- **Journal prompts** — generates 4 personalised prompts based on last 3 entries
- **Journal routes** — `POST /journal`, `GET /journal-prompts`, `GET /journal-logs`, `GET /journal-logs/{log_id}`, `DELETE /journal-logs/{log_id}` (delete removes both MongoDB + Pinecone)
- **`get_journal_context` tool** — chat agent can now semantically search past journal entries for deeper conversation context
- `journal_utils.py` — dedicated DB utils for journal collection
- `aura_postman.json` — Postman collection covering all routes

### Changed
- `POST /chat` — `email` removed from request body, now read from JWT token
- `GET /chat_history/{email}` → `GET /chat-history` — email from token, path param removed
- Chat agent tool dispatch refactored from if/elif chain to a `tool_dispatch` dict
- User routes split into `user_sub_routes/` (profile, chat, vision, voice, journal)
- Journal prompt tuned — summaries in neutral third-person for semantic search; `theme` is now a single string; prompts capped at 15 words
