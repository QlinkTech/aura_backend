# System Architecture

## 1. Overview

Aura ("Sanaya Aura" / internally titled "Menifest my dreams - qlink") is the
backend for an AI companion app focused on emotional regulation and
manifestation practices. It's a FastAPI service that serves the end-user
mobile/web app (chat, journaling, guided visualization, EFT tapping, vision
boards, voice) and an internal admin dashboard (user management, WhatsApp
campaigns/inbox, knowledge base, masterclasses, subscriptions). It also
receives inbound webhooks from WhatsApp (via Gupshup) and Razorpay
(payments).

## 2. Components

- **API layer** (`app/routes/`) — FastAPI routers, split by audience:
  - `auth` — signup/login, Google OAuth, phone OTP
  - `user` + `user_sub_routes/` — chat, journal, EFT, guided visualization,
    vision board, voice, profile, masterclass, resources, notifications,
    SSE event stream (`events.py`)
  - `systems` + `system_sub_routes/` — admin-only: user management, stats,
    knowledge base (kb), WhatsApp campaigns/templates/inbox, masterclass
    and resource management, prompt management, notifications
  - `payment` — Razorpay checkout + subscription webhooks
  - `whatsapp_webhook` — inbound Gupshup webhook (messages, delivery
    status)
- **Agents** (`app/core/`) — the conversational/generative logic:
  - `agent.py` — the main chat agent and shared embedding helper
  - `eft_agent/`, `guided_viz_agent/`, `journal_agent/` — specialized
    conversational flows, each with its own prompt/utils module
  - `vision_board/` — vision board question flow and image-prompt
    generation
- **Services** (`app/services/`) — integration and cross-cutting logic:
  - `auth_service.py` — JWT issuing/validation (PyJWT)
  - `event_bus.py` — in-process async pub/sub used to push real-time
    updates (chat, WhatsApp inbox) to connected clients over SSE
  - `payment_gateway/` — Razorpay client, subscription reconciliation,
    access sync (granting/revoking app access based on subscription state)
  - `gupshup/` — WhatsApp Business API client and message lifecycle
    handling
  - `mail/` — transactional email via Resend
  - `voice_service/` — speech-to-text (ElevenLabs) and Sarvam AI voice
    integration
  - `storage/` — file storage on Cloudflare R2, plus Cloudinary for media
  - `segmentation/` — user classification logic and an APScheduler-driven
    background scheduler (started/stopped in the FastAPI `lifespan` hook)
- **Data access** (`app/services/db/`) — one `*_utils.py` module per
  domain (users, journal, EFT, guided viz, notifications, chat sessions,
  WhatsApp templates/campaigns/inbox, phone OTP, activity log, Razorpay
  records), all built on `mongo_utils.py`. Vector storage for
  retrieval-augmented generation lives under `db/chroma/` (ChromaDB —
  the knowledge-base upload/search path in `system_sub_routes/kb.py`
  reads and writes here). `pinecone_utils.py` implements an equivalent
  KB/journal-embedding interface but has no current importers in
  `app/routes` or `app/core` — treat it as legacy/inactive rather than a
  second live vector store.
- **Datastores**: MongoDB (primary datastore, via `pymongo`), ChromaDB
  (active vector store for the knowledge base).

```mermaid
flowchart TB
    subgraph Clients
        MobileWeb["End-user app\n(mobile/web)"]
        Admin["Admin dashboard"]
        Gupshup["Gupshup\n(WhatsApp)"]
        Razorpay["Razorpay"]
    end

    subgraph API["FastAPI app (app/main.py)"]
        AuthR["auth routes"]
        UserR["user + user_sub_routes\n(chat, journal, EFT, guided-viz,\nvision, voice, profile, events)"]
        SysR["systems + system_sub_routes\n(users, stats, kb, whatsapp,\nmasterclass, prompt, notifications)"]
        PayR["payment routes"]
        WaWebhook["whatsapp_webhook route"]
    end

    subgraph Core["Agents (app/core)"]
        Agent["agent.py\n(main chat agent)"]
        EFT["eft_agent"]
        GuidedViz["guided_viz_agent"]
        Journal["journal_agent"]
        VisionBoard["vision_board"]
    end

    subgraph Services["Services (app/services)"]
        AuthSvc["auth_service\n(JWT)"]
        EventBus["event_bus\n(in-process pub/sub -> SSE)"]
        PaymentSvc["payment_gateway\n(Razorpay client, reconcile, access_sync)"]
        GupshupSvc["gupshup client\n(WhatsApp API)"]
        MailSvc["mail (Resend)"]
        VoiceSvc["voice_service\n(ElevenLabs, Sarvam)"]
        StorageSvc["storage\n(Cloudflare R2, Cloudinary)"]
        Segmentation["segmentation\n(classify + APScheduler)"]
    end

    subgraph Data["Data access (app/services/db)"]
        Mongo[("MongoDB\nper-domain *_utils.py")]
        Chroma[("ChromaDB\nknowledge base vectors")]
    end

    subgraph LLMs["External LLMs"]
        OpenAI["OpenAI"]
        Gemini["Google Gemini"]
    end

    MobileWeb --> AuthR & UserR & PayR
    Admin --> SysR
    Gupshup --> WaWebhook
    Razorpay --> PayR

    UserR --> AuthSvc
    UserR --> Agent
    UserR --> EFT
    UserR --> GuidedViz
    UserR --> Journal
    UserR --> VisionBoard
    UserR --> VoiceSvc
    UserR --> EventBus

    SysR --> AuthSvc
    SysR --> Chroma
    SysR --> GupshupSvc
    SysR --> EventBus
    SysR --> StorageSvc

    PayR --> PaymentSvc
    WaWebhook --> Mongo
    WaWebhook --> EventBus

    Agent --> OpenAI
    Agent --> Gemini
    Agent --> Chroma
    EFT --> OpenAI
    GuidedViz --> OpenAI
    Journal --> OpenAI
    VisionBoard --> OpenAI

    Agent --> Mongo
    EFT --> Mongo
    GuidedViz --> Mongo
    Journal --> Mongo
    PaymentSvc --> Mongo
    Segmentation --> Mongo
    MailSvc -.-> Mongo

    Segmentation -. "background jobs\n(FastAPI lifespan)" .-> API

    EventBus -. "SSE push" .-> MobileWeb
    EventBus -. "SSE push" .-> Admin
```

## 3. Data flow

**Chat (main path):** client sends a message with a JWT →
`auth_service` validates the token → the relevant route in
`user_sub_routes/chat.py` loads session/user context from MongoDB →
`app/core/agent.py` (or a specialized agent for EFT/journal/guided-viz)
calls out to an LLM (OpenAI or Gemini) and, for knowledge-base-grounded
replies, fetches relevant chunks from ChromaDB → the reply and any
side-effects (journal entry, session update) are written back to MongoDB
→ the response is returned to the client, with real-time pushes (e.g. new
message, status update) fanned out to subscribed clients via
`event_bus.py` over SSE (`user_sub_routes/events.py`).

```mermaid
sequenceDiagram
    participant C as Client (app)
    participant R as chat route
    participant A as auth_service
    participant Ag as agent.py
    participant Chroma as ChromaDB
    participant LLM as OpenAI / Gemini
    participant Mongo as MongoDB
    participant EB as event_bus (SSE)
    participant Other as Other subscribed clients

    C->>R: POST message (JWT)
    R->>A: validate token
    A-->>R: user identity
    R->>Mongo: load session/user context
    R->>Ag: generate reply
    Ag->>Chroma: fetch relevant KB chunks (if grounded)
    Chroma-->>Ag: chunks
    Ag->>LLM: completion request
    LLM-->>Ag: reply
    Ag->>Mongo: persist reply / journal / session update
    R-->>C: response
    R->>EB: publish event
    EB-->>Other: SSE push (new message / status)
```

**WhatsApp:** Gupshup posts inbound messages/delivery events to
`whatsapp_webhook_router` → stored via `whatsapp_inbox_utils.py` /
`whatsapp_template_utils.py` in MongoDB → published on `event_bus` so the
admin dashboard's WhatsApp inbox updates live over SSE
(`system_sub_routes/whatsapp_inbox.py`). Outbound campaign sends go the
other direction: admin action → `gupshup` client → Gupshup API.

```mermaid
sequenceDiagram
    participant GS as Gupshup
    participant WH as whatsapp_webhook route
    participant Mongo as MongoDB
    participant EB as event_bus (SSE)
    participant Admin as Admin dashboard
    participant GC as gupshup client

    GS->>WH: inbound message / delivery status
    WH->>Mongo: store in whatsapp_inbox / templates
    WH->>EB: publish event
    EB-->>Admin: SSE push (inbox updates live)

    Admin->>GC: send reply / campaign message
    GC->>GS: outbound WhatsApp API call
```

**Payments:** Razorpay checkout is initiated via `payment_gateway/client.py`;
Razorpay's webhook hits `payment` routes → `subscription_reconcile.py`
updates subscription state in MongoDB → `access_sync.py` grants/revokes
app access accordingly.

```mermaid
sequenceDiagram
    participant C as Client (app)
    participant P as payment routes
    participant PG as payment_gateway/client
    participant RP as Razorpay
    participant Rec as subscription_reconcile
    participant Mongo as MongoDB
    participant Sync as access_sync

    C->>P: initiate checkout
    P->>PG: create order
    PG->>RP: checkout API call
    RP-->>C: checkout flow (hosted by Razorpay)
    RP->>P: webhook (payment/subscription event)
    P->>Rec: reconcile subscription
    Rec->>Mongo: update subscription state
    Rec->>Sync: trigger access sync
    Sync->>Mongo: grant/revoke app access
```

**Background jobs:** the FastAPI `lifespan` hook starts an APScheduler
instance (`segmentation/scheduler.py`) that periodically re-classifies
users (`segmentation/classify.py`) independent of any request.

```mermaid
sequenceDiagram
    participant App as FastAPI lifespan
    participant Sched as APScheduler
    participant Classify as segmentation/classify
    participant Mongo as MongoDB

    App->>Sched: start_scheduler() on startup
    loop on schedule
        Sched->>Classify: run classification job
        Classify->>Mongo: read user activity/profile
        Classify->>Mongo: write updated segment
    end
    App->>Sched: stop_scheduler() on shutdown
```

## 4. External integrations & dependencies

- **LLMs**: OpenAI, Google Gemini (`google-genai`)
- **Vector store**: ChromaDB (active, knowledge base); Pinecone SDK is a
  dependency but its integration module is currently unused
- **Datastore**: MongoDB
- **Payments**: Razorpay (checkout + webhooks)
- **Messaging**: Gupshup (WhatsApp Business API — inbound webhook and
  outbound campaigns/replies)
- **Email**: Resend
- **Voice**: ElevenLabs (speech-to-text), Sarvam AI
- **Storage/media**: Cloudflare R2, Cloudinary
- **Auth**: Google OAuth (sign-in), PyJWT (session tokens), bcrypt/passlib
  (password hashing)

## 5. Tech stack

- **Language/runtime**: Python 3.10.13
- **Framework**: FastAPI on Uvicorn, ASGI lifespan used to start/stop the
  background scheduler and register the asyncio event loop with
  `event_bus`
- **Datastore**: MongoDB (via `pymongo`)
- **Background jobs**: APScheduler, in-process (no separate worker
  process/queue)
- **Containerization**: Docker (`Dockerfile`, `compose.yaml`,
  `docker-compose.yml`)
- **Real-time**: Server-Sent Events (`sse-starlette`) backed by an
  in-process pub/sub (`event_bus.py`) rather than an external broker

## 6. Key architectural decisions

- **Real-time updates use in-process SSE pub/sub, not an external message
  broker.** `event_bus.py` keeps subscriber queues in memory, keyed by
  user email, and requires the app's asyncio loop to be registered at
  startup. This is simple and sufficient for a single-instance deployment,
  but it means events don't fan out across multiple app instances/replicas
  — worth revisiting before horizontally scaling this service.
- **Background scheduling runs inside the API process.** `start_scheduler`/
  `stop_scheduler` are tied to the FastAPI lifespan, so segmentation jobs
  run in the same process serving requests rather than a separate worker.
  Simple to operate at current scale; a `--reload`/multi-worker deployment
  would need to guard against running the scheduler more than once.
- **Two vector-store integrations exist, only one is live.** ChromaDB
  backs the knowledge-base RAG path in production use; `pinecone_utils.py`
  implements an equivalent interface (including journal embeddings) but
  has no current callers. Anyone touching KB/RAG code should confirm
  which store is intended before extending either.
