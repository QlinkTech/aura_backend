# Changelog

All notable changes to Aura are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Admin Dashboard — Stats] - 2026-08-18
_Author: Pratham Paleriya_

### Changed
- **The stats page now reports one clear answer per number instead of two conflicting ones.** It previously showed two parallel user breakdowns side by side that used the same words to mean different things — "free" meant "on the free plan" in one and "free plan expired" in the other, and manually-comped accounts were pulled out of their category in only one of the two. Both added up to the right total while disagreeing on every line, which made the page impossible to read honestly. There is now a single funnel: signed up only, abandoned checkout, on trial, trial expired, paying, cancelled-but-still-active, and churned. Every user falls into exactly one of these, and they always add up to the total.
- **Feature usage is now comparable across features.** Each of chat, EFT tapping, guided visualization, vision board and journal reports the same three things — how many people used it, what share of the user base that is, and how often they came back — so they can be ranked against each other at a glance. Previously each feature reported a slightly different set of numbers.

### Added
- **Manually-granted (comped) accounts can now be left out of the numbers.** Team members, testers and friends given free access have never had to convert and their usage isn't customer behavior, so counting them quietly distorted every conversion and adoption figure. They are now excluded by default — still counted in the total user count and shown separately — with a toggle to fold them back in. On current data this is the difference between chat looking like 135 sessions and actually being 72 from real users.
- **Every number on the page can be opened to see the people behind it.** Clicking any figure — trial expired, churned, dormant, anyone who has used the journal — lists those exact users with their contact details, so an admin can act on a number instead of just reading it.
- **A "needs attention" list of things worth doing today**, each already carrying the users it refers to: trials expiring within seven days, subscriptions halted after repeated failed payments, cancelled accounts still inside their paid window, and any vision board or guided visualization that failed to generate.
- **Revenue is now reported alongside usage** — total captured, this month's, average payment, success/failure rate on payment attempts, how many distinct people have ever paid, and the split across plans. Note that captured-payment counts still include the ₹1/₹5 gateway test transactions, which inflates the payment count without meaningfully affecting the revenue figure.
- **A weekly and monthly active-user count, and a dormant count** — people who signed up but haven't opened anything in over a month.

*(Backend complete; live once the dashboard's frontend is wired up to it.)*

---

## [Chat Assistant — Model Upgrade] - 2026-08-18
_Author: Pratham Paleriya_

### Changed
- **The assistant now runs on a newer, more capable underlying model.** No change to its persona, rules or behavior instructions — the same guidance, better reasoning behind it.

---

## [EFT Tapping — Audio Generation] - 2026-08-17
_Author: Pratham Paleriya_

### Fixed
- **Longer tapping sessions were being cut short in the audio.** The whole script was sent to the voice service in one request, and anything past its length limit was silently dropped — so a user could be left with audio that stops partway through the session. The script is now split at paragraph boundaries into pieces the service can handle and the audio is joined back together, with no gap inserted, so it plays as one continuous take regardless of length.

### Changed
- **Tapping sessions are now written to run about 5 minutes instead of 2–4**, giving a fuller session rather than one that ends before the user has settled into it.
- **Reverted an attempt to give the tapping voice an Indian accent.** The approach respelled the English script in Devanagari letters so the voice would read English words with an Indian pronunciation, but it kept drifting into actually translating the words into Hindi, which is not what a user asked for. The script is now read as written in English while a better approach is found.

---

## [Chat Assistant — Question Pacing] - 2026-08-12
_Author: Pratham Paleriya_

### Changed
- **The assistant no longer ends nearly every reply with a question.** Its persona instructions told it to close each message with a powerful question, and taken literally that turned conversations into an intake form — question after question, with the user doing all the work and never receiving anything back. Questions are now the deliberate exception rather than the default close: at most one per reply, never twice in a row, and roughly two or three across an entire conversation before it has to stop gathering and start actually coaching. Most replies now end by reflecting back what it's seeing, or by giving the person the teaching or practice they came for.

---

## [Notifications — WhatsApp Delivery] - 2026-08-10
_Author: Pratham Paleriya_

### Added
- **Five notifications that previously only existed inside the web app now also arrive on WhatsApp.** Until now a user only found out that their guided visualisation, EFT tapping session or vision board had finished generating — or that a new masterclass or resource had gone live — if they happened to have the app open, or opened it again later. Since the generative ones take a few minutes, that often meant the user had already closed the tab and never came back to it. The same five moments are now sent to WhatsApp as short utility messages, for any user who has verified a phone number. Each one carries a button that opens the exact thing it's about — the specific visualisation or tapping session that just finished, the specific resource that just went live — rather than a generic landing page. The in-app notification is unchanged and still fires regardless — a WhatsApp failure never affects it. Users who never verified a number simply keep the in-app-only experience. *(Backend complete; the WhatsApp side stays dormant until Meta approves the five message templates — until then nothing is sent and nothing breaks.)*
- **A masterclass broadcast on WhatsApp only goes out when there is genuinely something new to announce** — a new masterclass, or a change to its title or scheduled time. Correcting the meeting link, ID or password no longer messages everyone again. (The in-app notification still fires on every save, as before.)

---

## [Subscriptions — Free Plan Length] - 2026-08-07
_Author: Pratham Paleriya_

### Changed
- **The free plan is 7 days again, after briefly being set to 30.** A configuration change had extended it to a full month, which is far longer than the intended trial and delayed the point at which anyone is asked to pay. Anyone who activated a free plan during that window keeps the longer access they were already given — the change applies to new activations only.

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

---

## [Subscriptions — Plans & Lapsed Access] - 2026-07-30
_Author: Pratham Paleriya_

### Added
- **A 1-month subscription plan is now available**, alongside the existing options.

### Fixed
- **Two subscription plans were pointing at the wrong plan IDs at the payment gateway**, meaning a checkout could be created against the wrong plan. Corrected.
- **Users whose subscription had lapsed could keep their paid access indefinitely.** Access was only re-checked when a payment webhook happened to arrive, so a cancelled, paused or expired free plan whose window had passed often left the account still marked as paying. Access is now re-evaluated on every login and every authenticated request, using one shared rule, so it ends when it should. Importantly, cancelling does not cut access off early — someone who cancels but has already paid through to a future date keeps access until that date, since cancelling means "won't renew", not "ends now".
- **Payment and subscription webhooks arriving out of order could leave an account in the wrong state.** Razorpay does not guarantee delivery order, so a later event could be overwritten by an earlier one arriving afterwards. Events are now reconciled against the gateway's own current state rather than trusted in arrival order.

<img src="assets/hue-bar.svg" width="100%" height="4" alt=""/>
