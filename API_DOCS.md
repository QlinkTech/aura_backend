# Aura Server — API Documentation

Base URL: `/api`

---

## Auth Routes — `/api/auth`

---

### POST `/api/auth/register`
Create a new user account.

**Request Body**
```json
{
  "email": "user@example.com",
  "password": "secret123"
}
```

**Response — 200 OK**
```json
{
  "message": "Account created successfully",
  "access_token": "<jwt_token>",
  "token_type": "bearer"
}
```

**Error Responses**
| Status | Detail |
|--------|--------|
| 400 | Email already registered |
| 500 | Internal server error |

---

### POST `/api/auth/login`
Login with email and password.

**Request Body**
```json
{
  "email": "user@example.com",
  "password": "secret123"
}
```

**Response — 200 OK**
```json
{
  "access_token": "<jwt_token>",
  "token_type": "bearer"
}
```

**Error Responses**
| Status | Detail |
|--------|--------|
| 401 | Invalid credentials |
| 500 | Internal server error |

---

### POST `/api/auth/generate-vision`
Onboard a new user — sets password, creates profile, and queues vision board generation in the background.

**Request Body**
```json
{
  "email": "user@example.com",
  "name": "Jane Doe",
  "password": "secret123",
  "answers": {
    "question_1": "answer_1"
  },
  "vibe": {
    "color": "gold",
    "mood": "abundance"
  }
}
```

**Response — 200 OK**
```json
{
  "access_token": "<jwt_token>",
  "token_type": "bearer"
}
```

> Vision board generation runs asynchronously. Poll `/api/user/vision-board/{email}` to check status. URL will be `"preparing"` until ready.

---

### POST `/api/auth/check-user`
Check if a user exists by email.

**Request Body**
```json
{
  "email": "user@example.com"
}
```

**Response — 200 OK**
```json
{
  "exists": true
}
```

---

### POST `/api/auth/reset-password`
Reset a user's password.

**Request Body**
```json
{
  "email": "user@example.com",
  "new_password": "newSecret123"
}
```

**Response — 200 OK**
```json
{
  "message": "Password reset successfully"
}
```

**Error Responses**
| Status | Detail |
|--------|--------|
| 404 | User not found |
| 500 | Internal server error |

---

## User Routes — `/api/user`

> All user routes require `Authorization: Bearer <token>` header.

---

### GET `/api/user/vision-board/{email}`
Get the vision board URL for a user.

**Path Params**
| Param | Type | Description |
|-------|------|-------------|
| email | string | User's email |

**Response — 200 OK**
```json
{
  "vision_board_url": "https://res.cloudinary.com/..."
}
```

> Returns `"preparing"` as the URL while generation is in progress, and `"failed"` if generation failed.

**Error Responses**
| Status | Detail |
|--------|--------|
| 403 | Forbidden (token email mismatch) |
| 404 | Vision board not found |

---

### POST `/api/user/chat`
Send a message to the AI coach.

**Request Body**
```json
{
  "email": "user@example.com",
  "message": "I feel stuck with my manifestation goals."
}
```

**Response — 200 OK**
```json
{
  "reply": "Hi love, I hear you..."
}
```

**Error Responses**
| Status | Detail |
|--------|--------|
| 400 | Agent processing error |
| 403 | Forbidden / No user found |

---

### GET `/api/user/chat_history/{email}`
Fetch full chat history for a user.

**Path Params**
| Param | Type | Description |
|-------|------|-------------|
| email | string | User's email |

**Response — 200 OK**
```json
[
  { "role": "user", "content": "Hello" },
  { "role": "assistant", "content": "Hi love..." }
]
```

**Error Responses**
| Status | Detail |
|--------|--------|
| 403 | Forbidden |
| 404 | User not found |

---

### POST `/api/user/regenerate-vision`
Re-generate the vision board for an existing user.

**Request Body**
```json
{
  "email": "user@example.com",
  "answers": {
    "question_1": "answer_1"
  },
  "vibe": {
    "color": "purple",
    "mood": "clarity"
  }
}
```

**Response — 200 OK**
```json
{
  "sucess": true,
  "token_type": "bearer"
}
```

> Generation runs in the background. Poll `/api/user/vision-board/{email}` for the result.

**Error Responses**
| Status | Detail |
|--------|--------|
| 403 | Forbidden |

---

### GET `/api/user/user-profile?email={email}`
Get user profile details (excludes chat history and internal ID).

**Query Params**
| Param | Type | Description |
|-------|------|-------------|
| email | string | User's email |

**Response — 200 OK**
```json
{
  "email": "user@example.com",
  "name": "Jane Doe",
  "is_paid": false,
  "vision_board_url": "https://...",
  "subscription_status": "active",
  "early_bird_sub_id": "sub_xxx",
  "early_bird_plan_key": "3_months_plan",
  "created_at": 1700000000,
  "updated_at": 1700000001
}
```

---

## Payment Routes — `/api/payment`

---

### POST `/api/payment/early-bird-subscription`
Create or retrieve an early bird subscription payment link.

> Requires `X-API-Key: <admin_api_key>` header.

**Request Body**
```json
{
  "email": "user@example.com",
  "plan_key": "3_months_plan",
  "expire_by": 1800000000
}
```

**Available plan keys**
| Key | Billing | Total Cycles |
|-----|---------|-------------|
| `3_months_plan` | Monthly | 40 |
| `1_year_plan` | Yearly | 10 |

> A 1-month free trial is applied — billing starts 1 month from subscription creation (`start_at`).

**Response — 200 OK**
```json
{
  "subscription_id": "sub_xxxxxxxxxxxxx",
  "payment_link": "https://rzp.io/l/xxx"
}
```

**Error Responses**
| Status | Detail |
|--------|--------|
| 400 | Subscription already paid |
| 400 | Invalid plan key |
| 403 | Invalid API key |
| 500 | Internal server error |

---

### POST `/api/payment/webhook`
Razorpay webhook receiver. Handles payment and subscription lifecycle events.

> Verified via `X-Razorpay-Signature` header (HMAC SHA256).

**Handled Events**
| Event | Action |
|-------|--------|
| `payment.captured` | Save payment, mark user `is_paid: true` |
| `payment.failed` | Save failed payment record |
| `subscription.activated` | Update subscription status to `active`, set `is_paid: true` |
| `subscription.charged` | Update subscription status to `active`, set `is_paid: true` |
| `subscription.authenticated` | Update subscription status to `authenticated`, set `is_paid: true` |
| `subscription.cancelled` | Update subscription status to `cancelled` |
| `subscription.completed` | Update subscription status to `completed` |
| `subscription.halted` | Update subscription status to `halted` |

**Response — 200 OK**
```json
{
  "status": "ok"
}
```

**Error Responses**
| Status | Detail |
|--------|--------|
| 400 | Invalid webhook signature |

---

## System Routes — `/api/system`

> Internal/dashboard routes.

---

### POST `/api/system/login`
Dashboard login.

**Request Body**
```json
{
  "username": "admin",
  "password": "secret"
}
```

**Response — 201**
```json
{ "success": true }
```

**Error Responses**
| Status | Detail |
|--------|--------|
| 401 | Missing credentials |
| 402 | Invalid username or password |

---

### GET `/api/system/prompt`
Get the current AI system prompt.

**Response — 200 OK**
```json
{
  "category": "system_prompt",
  "prompt": "You are Sanaya AI...",
  "old_prompt": "..."
}
```

---

### PUT `/api/system/prompt`
Update the AI system prompt.

**Request Body**
```json
{
  "prompt": "You are Sanaya AI, updated version..."
}
```

**Response — 200 OK**
```json
{ "success": true }
```

---

### POST `/api/system/kb/upload`
Upload a PDF file to the knowledge base.

**Form Data**
| Field | Type | Description |
|-------|------|-------------|
| file | PDF file | Must be `application/pdf` |

**Response — 200 OK**
```json
{
  "success": true,
  "chunks_uploaded": 12
}
```

**Error Responses**
| Status | Detail |
|--------|--------|
| 400 | Only PDF files allowed |
| 400 | PDF text is empty |

---

### POST `/api/system/kb/add-text`
Add raw text to the knowledge base.

**Request Body**
```json
{
  "text": "Chakra healing involves..."
}
```

**Response — 200 OK**
```json
{
  "success": true,
  "chunks_uploaded": 3
}
```

---

### GET `/api/system/kb/all`
List all knowledge base records.

**Response — 200 OK**
```json
[
  {
    "id": "doc_abc123",
    "metadata": {
      "text": "...",
      "created_at": "2024-01-01T00:00:00"
    }
  }
]
```

---

### GET `/api/system/kb/id/{doc_id}`
Get a single KB record by ID.

**Path Params**
| Param | Type | Description |
|-------|------|-------------|
| doc_id | string | Pinecone vector ID |

**Response — 200 OK**
```json
{
  "id": "doc_abc123",
  "metadata": {
    "text": "...",
    "created_at": "2024-01-01T00:00:00"
  }
}
```

**Error Responses**
| Status | Detail |
|--------|--------|
| 404 | record not found |

---

### PUT `/api/system/kb/update/{doc_id}`
Replace a KB record with new text (deletes old, re-chunks and re-embeds new).

**Path Params**
| Param | Type | Description |
|-------|------|-------------|
| doc_id | string | Pinecone vector ID to replace |

**Request Body**
```json
{
  "text": "Updated knowledge text..."
}
```

**Response — 200 OK**
```json
{ "success": true }
```

---

### DELETE `/api/system/kb/delete/{doc_id}`
Delete a KB record by ID.

**Path Params**
| Param | Type | Description |
|-------|------|-------------|
| doc_id | string | Pinecone vector ID |

**Response — 200 OK**
```json
{ "success": true }
```

---

### POST `/api/system/kb/search`
Semantic search across the knowledge base.

**Request Body**
```json
{
  "query": "root chakra healing"
}
```

**Response — 200 OK**
```json
[
  {
    "id": "doc_abc123",
    "text": "Root chakra is associated with...",
    "created_at": "2024-01-01T00:00:00"
  }
]
```

**Error Responses**
| Status | Detail |
|--------|--------|
| 404 | record not found |
| 500 | Failed to get records |

---

## Health Check

### GET `/ping`
Check if the server is running.

**Response — 200 OK**
```json
{
  "status": "ok",
  "message": "MMD - Qlink backend is running perfectly fine."
}
```
