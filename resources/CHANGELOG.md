# Changelog

All notable changes to Aura are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Account Access — Session Length] - 2026-08-05
_Author: Pratham Paleriya_

### Changed
- **Users now stay signed in for 30 days instead of 3** before being asked to log in again. Applies to every login method (email/password, sign-up, and Google sign-in). This supersedes the 1→3 day change from the previous day, which was still too short for normal usage patterns.

---

## [Admin Dashboard — WhatsApp Inbox] - 2026-08-05
_Author: Pratham Paleriya_

### Added
- **Admins can now see and reply to WhatsApp messages from any user, in one place.** Previously there was no way to view what a user sent us on WhatsApp, or to write back — messages could only go out in bulk, via pre-approved templates (campaigns). The new inbox lists every conversation by most recent activity and shows the full message history per phone number, including images and other attachments the user sent. Replies are written as free text and work only inside WhatsApp's 24-hour reply window for that conversation; once that window closes, the admin is prompted to send an approved template instead, which reopens the window once the user responds. New messages and delivery updates (sent/delivered/read) appear immediately, with no need to refresh. *(Backend complete; live once the dashboard's frontend is wired up to it.)*

---

## [Account Access — Session Length] - 2026-08-04
_Author: Pratham Paleriya_

### Changed
- **Users now stay signed in for 3 days instead of 1** before being asked to log in again. Applies to every login method (email/password, sign-up, and Google sign-in) — previously all of them expired after just one day, which meant unusually frequent re-logins for a normal usage pattern.

---

## [Aura Persona — "Aura" system prompt draft] - 2026-07-31
_Author: Pratham Paleriya_

### Added
- **Drafted a revised persona prompt ("V3"), not yet deployed.** The previous draft ("V2") directly contradicted several always-on behavior rules already running in production — reply length/pacing, when and how in-app features get mentioned, and how boundary-related advice must be handled. The new draft resolves those conflicts and folds in a companion set of behavior rules (nervous-system-first routing, a mandatory check-in before ever giving boundary-setting advice) that had been written but never actually wired into the live prompt. The old draft is kept on file for reference. This is a review artifact only — no change to what users experience until it's explicitly approved and pushed live.

---

## [Knowledge Base] - 2026-07-31
_Author: Pratham Paleriya_

### Changed
- **Migrated the knowledge base and user memory storage to a new vector database provider.** No change to what the assistant can answer. Fixes made during the move: memory records no longer store a user's email in plain text as part of the record ID, and a bulk-listing bug that could silently return incomplete results is corrected.
- **Admin knowledge base list is now paginated, searchable, and filterable by source document**, with a matching endpoint to populate the filter dropdown. Previously it returned every record at once with no way to search or filter.

### Added
- **Sanaya's teaching material is now ingested using its actual structure** (each named teaching becomes one complete, correctly-titled entry) instead of being sliced into fixed-length blocks that could cut a teaching in half. This directly improves answer quality — the assistant now retrieves whole, coherent teachings rather than fragments.

---

## [Admin Dashboard — User Management] - 2026-07-31
_Author: Pratham Paleriya_

### Fixed
- **Cancelled-but-still-active subscribers were mislabeled as "trial" users.** A user who paid, then cancelled, but is still inside their paid period was showing the same status as someone who never converted at all. They now show a distinct "cancelled, still active" status.
- **User search now also matches phone number**, not just email and username.

### Added
- **Admin can now see exactly when a user's access actually expires**, regardless of which underlying plan type they're on — previously this wasn't reliably visible for every plan type.

---

## [Chat Assistant — Accuracy & Grounding] - 2026-07-31
_Author: Pratham Paleriya_

### Fixed
- **The assistant was occasionally inventing specific techniques it presented as Sanaya's teaching** (a journaling template and a breathing exercise that don't exist in her actual material), and in a few cases had already saved these fabrications into a user's long-term memory, where they resurfaced as "remembered fact" in later conversations. The underlying causes are fixed: the assistant now searches based only on what the user actually said (not a guessed-at premise), and no longer treats its own earlier, unverified statements in a conversation as a trusted foundation to build further answers on. The specific fabricated memory entries already created have been removed.
- **Retrieved teaching material is now clearly attributed and separated within a reply**, so multi-topic answers no longer risk blending two unrelated teachings together.

---

## [Chat Assistant — In-App Feature Recommendations] - 2026-07-31
_Author: Pratham Paleriya_

### Changed
- **In-app feature suggestions (Journal, EFT Tapping, Guided Visualization, Vision Board, Resources) are now shown as a proper clickable card**, generated as structured data for the app to render, instead of being written as a plain link inside the chat reply text.
- **Feature suggestions are now rare and only at the truly obvious moment** — at most once per conversation, never as an opener, never for a short/low-effort message. Previously these were surfacing too often and could interrupt an ongoing piece of coaching.

### Fixed
- **The assistant would sometimes walk a user through an entire technique (e.g. a full EFT tapping script) without ever pointing them to the matching in-app tool built for exactly that.** It now recognizes that moment as the clear signal to do so.

---

## [Chat Assistant — Reliability] - 2026-07-31
_Author: Pratham Paleriya_

### Changed
- **Modernized the assistant's underlying model-calling integration** to a more current, structured calling method. Session-title generation and the "conversation starter" suggestions now use schema-enforced output, reducing the chance of a malformed response causing a silent failure.

<img src="assets/hue-bar.svg" width="100%" height="4" alt=""/>
