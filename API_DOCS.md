# Aura Server — API Documentation

## Authentication

All **user routes** (`/user/*`) require:
1. A valid JWT bearer token — `Authorization: Bearer <token>`
2. An active Razorpay subscription (`subscription_status: active/completed` or `is_paid: true`)

Requests that fail auth return:
- `401` — missing/expired/invalid token
- `403` — authenticated but no active subscription
- `404` — user not found

---

## Auth Routes — `/auth`

No authentication required.

---

### `POST /auth/register`

Create a new user account.

**Body**
```json
{ "email": "string", "password": "string" }
```

**Response `200`**
```json
{ "message": "Account created successfully", "access_token": "string", "token_type": "bearer" }
```

**Errors**
- `400` — email already registered

---

### `POST /auth/login`

Login with email and password.

**Body**
```json
{ "email": "string", "password": "string" }
```

**Response `200`**
```json
{ "access_token": "string", "token_type": "bearer" }
```

**Errors**
- `401` — invalid credentials

---

### `POST /auth/check-user`

Check if an email is already registered.

**Body**
```json
{ "email": "string" }
```

**Response `200`**
```json
{ "exists": true }
```

---

### `POST /auth/reset-password`

Reset password for an existing user.

**Body**
```json
{ "email": "string", "new_password": "string" }
```

**Response `200`**
```json
{ "message": "Password reset successfully" }
```

**Errors**
- `404` — user not found

---

## User Routes — `/user`

All routes require `Authorization: Bearer <token>` and an active subscription.

---

### `GET /user/vision-board/{email}`

Get the vision board URL for a user.

**Path Params**
- `email` — must match the authenticated user

**Response `200`**
```json
{ "vision_board_url": "string" }
```

**Errors**
- `403` — token email doesn't match path email
- `404` — vision board not found

---

### `POST /user/generate-vision`

Generate a vision board for the authenticated user. Email is taken from the token — no body field needed.

**Body**
```json
{
  "answers": { "...": "..." },
  "vibe": { "...": "..." }
}
```

**Response `200`**
```json
{ "success": true }
```

> Vision board generation runs in the background. Poll `GET /user/vision-board/{email}` to check when it's ready (value changes from `"preparing"` to a URL).

---

### `POST /user/regenerate-vision`

Regenerate the vision board for a user.

**Body**
```json
{
  "email": "string",
  "answers": { "...": "..." },
  "vibe": { "...": "..." }
}
```

**Response `200`**
```json
{ "success": true }
```

**Errors**
- `403` — token email doesn't match body email

---

### `POST /user/chat`

Send a message to the AI agent.

**Body**
```json
{ "email": "string", "message": "string" }
```

**Response `200`**
```json
{ "reply": "string" }
```

**Errors**
- `400` — agent returned an error
- `403` — token email doesn't match body email

---

### `GET /user/chat_history/{email}`

Retrieve the full chat history for a user.

**Path Params**
- `email` — must match the authenticated user

**Response `200`**
```json
[
  { "role": "user", "content": "string" },
  { "role": "assistant", "content": "string" }
]
```

**Errors**
- `403` — token email doesn't match path email
- `404` — user not found

---

### `GET /user/user-profile`

Get user profile details (excludes chat history).

**Query Params**
- `email` — email of the user to fetch

**Response `200`**
```json
{
  "email": "string",
  "is_paid": true,
  "subscription_status": "active",
  "vision_board_url": "string",
  "created_at": 0,
  "updated_at": 0
}
```

---

### `POST /user/voice-to-text`

Transcribe an audio file to text.

**Body** — `multipart/form-data`
- `audio` — audio file

**Supported types:** `audio/wav`, `audio/mpeg`, `audio/mp4`, `audio/webm`, `audio/ogg`, `audio/x-m4a`
**Max size:** 10 MB

**Response `200`**
```json
{ "transcript": "string" }
```

**Errors**
- `400` — unsupported file type
- `413` — file exceeds 10 MB
- `500` — transcription failed

---

## Payment Routes — `/payment`

---

### `POST /payment/early-bird-subscription`

Create a Razorpay subscription link for an early bird user.

**Auth** — requires `X-API-Key` header (admin key)

**Body**
```json
{
  "email": "string",
  "plan_key": "3_months_plan | 1_year_plan",
  "expire_by": 1234567890
}
```
> `expire_by` is optional — Unix timestamp for link expiry.

**Response `200`**
```json
{ "subscription_id": "string", "payment_link": "string" }
```

**Errors**
- `400` — invalid plan key or subscription already paid
- `403` — invalid API key

---

### `POST /payment/webhook`

Razorpay webhook receiver. Handles payment and subscription lifecycle events.

**Auth** — validated via `X-Razorpay-Signature` header (HMAC-SHA256)

**Handled events**

| Event | Effect |
|---|---|
| `payment.captured` / `payment.authorized` | Saves payment, sets `is_paid: true` |
| `payment.failed` | Saves failed payment record |
| `subscription.authenticated` | Sets status `active`, `is_paid: true` |
| `subscription.activated` | Sets status `active`, `is_paid: true` |
| `subscription.charged` | Sets status `active`, `is_paid: true` |
| `subscription.resumed` | Sets status `active`, `is_paid: true` |
| `subscription.completed` | Sets status `completed`, `is_paid: false` |
| `subscription.cancelled` | Sets status `cancelled`, `is_paid: false` |
| `subscription.halted` | Sets status `halted`, `is_paid: false` |
| `subscription.pending` | Sets status `pending`, `is_paid: false` |
| `subscription.paused` | Sets status `paused`, `is_paid: false` |

**Response `200`**
```json
{ "status": "ok" }
```

**Errors**
- `400` — invalid webhook signature

---

## System Routes — `/system`

Admin/dashboard routes. No user-level auth — protected by basic username/password login.

---

### `POST /system/login`

Dashboard login.

**Body**
```json
{ "username": "string", "password": "string" }
```

**Response `201`**
```json
{ "success": true }
```

**Errors**
- `401` — missing credentials
- `402` — invalid username or password

---

### `GET /system/prompt`

Get the current system prompt.

**Response `200`**
```json
{ "category": "system_prompt", "prompt": "string", "old_prompt": "string" }
```

---

### `PUT /system/prompt`

Update the system prompt.

**Body**
```json
{ "prompt": "string" }
```

**Response `200`**
```json
{ "success": true }
```

---

### `POST /system/kb/upload`

Upload a PDF to the knowledge base. Text is chunked and embedded into Pinecone.

**Body** — `multipart/form-data`
- `file` — PDF file (`application/pdf` only)

**Response `200`**
```json
{ "success": true, "chunks_uploaded": 12 }
```

---

### `POST /system/kb/add-text`

Add raw text to the knowledge base.

**Body**
```json
{ "text": "string" }
```

**Response `200`**
```json
{ "success": true, "chunks_uploaded": 4 }
```

---

### `GET /system/kb/all`

List all knowledge base records.

**Response `200`** — array of KB records

---

### `GET /system/kb/id/{doc_id}`

Fetch a single KB record by ID.

**Errors**
- `404` — record not found

---

### `PUT /system/kb/update/{doc_id}`

Replace a KB record with new text. Old chunks are deleted; new chunks are embedded.

**Body**
```json
{ "text": "string" }
```

**Response `200`**
```json
{ "success": true }
```

---

### `DELETE /system/kb/delete/{doc_id}`

Delete a KB record by ID.

**Response `200`**
```json
{ "success": true }
```

---

### `POST /system/kb/search`

Semantic search over the knowledge base.

**Body**
```json
{ "query": "string" }
```

**Response `200`** — top 15 matching records

**Errors**
- `404` — no results found
- `500` — search failed
