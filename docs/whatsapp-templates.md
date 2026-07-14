# WhatsApp Template & Campaign Management API

Admin-only routes for creating and managing WhatsApp message templates, and for sending them out as campaigns, through the Gupshup Partner API. All routes live under `app/routes/system_sub_routes/whatsapp.py` and are mounted at:

```
/api/system/whatsapp/...
```

They use the app's single configured Gupshup app (`GUPSHUP_APP_ID` / `GUPSHUP_TOKEN` env vars) — there is no per-request appId/token, so these routes always operate on the same WABA.

---

## Authentication

Every route below requires a valid **admin (system) JWT**, the same one used by the rest of the `/api/system` dashboard.

1. Log in first:

   ```
   POST /api/system/login
   Content-Type: application/json

   { "username": "...", "password": "..." }
   ```

   Response: `{ "success": true, "access_token": "...", "token_type": "bearer" }`

2. Send that token on every request below:

   ```
   Authorization: Bearer <access_token>
   ```

If the token is missing/expired/invalid you'll get a `401`. If it's valid but not a system-role token, you'll get a `403 "System access only"`.

---

## Endpoints at a glance

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/system/whatsapp/templates` | Apply for (create) a template |
| GET | `/api/system/whatsapp/templates` | List / search templates |
| PUT | `/api/system/whatsapp/templates/{template_id}` | Edit an existing template |
| DELETE | `/api/system/whatsapp/templates/{element_name}` | Permanently delete a template |
| POST | `/api/system/whatsapp/templates/media` | Upload sample media, get a `handleId` |
| GET | `/api/system/whatsapp/campaigns/personalization-fields` | List fields available for per-recipient params |
| POST | `/api/system/whatsapp/campaigns` | Trigger a template-message campaign |
| GET | `/api/system/whatsapp/campaigns` | List campaigns with delivery stats |
| GET | `/api/system/whatsapp/campaigns/{campaign_id}` | Campaign detail + stats |
| GET | `/api/system/whatsapp/campaigns/{campaign_id}/contacts` | Per-contact delivery breakdown |
| POST | `/api/whatsapp/webhook` | *(public, no auth)* Gupshup delivery-event callback |

---

## 1. Create a template — `POST /whatsapp/templates`

Body is JSON (not form-encoded — the server translates it to Gupshup's expected `application/x-www-form-urlencoded` request internally).

### Fields

| Field | Required | Default | Notes |
|---|---|---|---|
| `element_name` | ✅ | — | Unique template name within your WABA namespace |
| `category` | ✅ | — | `AUTHENTICATION` \| `MARKETING` \| `UTILITY` |
| `content` | ✅ | — | Template body. Max 1024 chars. For `AUTHENTICATION`, first line must be like `{{1}} is your verification code.` |
| `example` | ✅ | — | Example text showing filled-in placeholders |
| `template_type` | optional | `"TEXT"` | `TEXT`, `IMAGE`, `VIDEO`, `DOCUMENT`, `LOCATION`, `PRODUCT`, `CATALOG`, `LTO`, `CAROUSEL` |
| `vertical` | optional | `"TEXT"` | Free-text vertical/industry label |
| `language_code` | optional | `"en_US"` | See [Gupshup language codes](https://support.gupshup.io/hc/en-us/articles/360013321939) |
| `header` | optional | — | Max 60 chars. Not valid for `AUTHENTICATION` |
| `footer` | optional | — | Max 60 chars. Not valid for `AUTHENTICATION` |
| `example_header` | optional | — | Example text for the header |
| `example_media` | optional | — | `handleId` from the [media upload endpoint](#5-upload-sample-media--post-whatsapptemplatesmedia) — required for `IMAGE`/`VIDEO`/`DOCUMENT` template types with sample media |
| `buttons` | optional | — | A JSON array (list of objects), e.g. `[{"type":"PHONE_NUMBER","text":"Call Us","phone_number":"+919872329959"}]`. For `AUTHENTICATION`, use OTP-type buttons instead (see Gupshup docs) |
| `enable_sample` | optional | `true` | Whether a sample is supplied |
| `allow_template_category_change` | optional | `false` | Let Meta auto-correct a miscategorized template |
| `add_security_recommendation` | optional | — | `AUTHENTICATION` only — appends "For your security, do not share this code" |
| `code_expiration_minutes` | optional | — | `AUTHENTICATION` only — 1 to 90 |
| `message_send_ttl_seconds` | optional | — | Message validity window. Auth: 30–900s · Utility: 30–43200s · Marketing: 43200–2592000s |
| `is_cpr` | optional | — | Enable/disable Call Permission Request |
| `parameter_format` | optional | — | `NAMED` or `POSITIONAL` (defaults to positional on Gupshup's side) |

### Example — plain text template

```bash
curl -X POST '{{BASE_URL}}/api/system/whatsapp/templates' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}' \
  -H 'Content-Type: application/json' \
  -d '{
    "element_name": "order_confirmation",
    "category": "UTILITY",
    "content": "Your order {{1}} is confirmed and will arrive by {{2}}.",
    "example": "Your order 12345 is confirmed and will arrive by 2026-07-15.",
    "header": "Order Update",
    "footer": "Thanks for shopping with us",
    "buttons": [
      { "type": "PHONE_NUMBER", "text": "Call Us", "phone_number": "+919872329959" }
    ]
  }'
```

### Example — image template (with sample media)

First upload media to get a `handleId` (see [section 5](#5-upload-sample-media--post-whatsapptemplatesmedia)), then:

```bash
curl -X POST '{{BASE_URL}}/api/system/whatsapp/templates' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}' \
  -H 'Content-Type: application/json' \
  -d '{
    "element_name": "promo_banner",
    "category": "MARKETING",
    "template_type": "IMAGE",
    "content": "Check out our sale {{1}}!",
    "example": "Check out our sale this weekend!",
    "example_media": "4::aW1hZ2UvcadG5n:ARYaMMMA2Qv...<handleId>"
  }'
```

### Response — `201`/`200`

```json
{
  "success": true,
  "status": "success",
  "template": {
    "id": "5da48971-6181-4c45-8de0-c786a93328e7",
    "elementName": "order_confirmation",
    "status": "PENDING",
    "category": "UTILITY",
    "templateType": "TEXT",
    "...": "..."
  }
}
```

New templates always come back with `status: "PENDING"` — Meta review happens asynchronously. Poll [Get Templates](#2-list-templates--get-whatsapptemplates) to check approval status.

### Errors
- `500` — Gupshup not configured (missing env vars)
- `502` — Gupshup rejected the request (bad category, name already exists, invalid content, etc.) — check `detail` for Gupshup's raw error message

---

## 2. List templates — `GET /whatsapp/templates`

All filters are optional query params; omit what you don't need.

| Query param | Type | Notes |
|---|---|---|
| `template_type` | string | e.g. `TEXT`, `IMAGE`, `CAROUSEL` |
| `status` | string | `PENDING`, `APPROVED`, `REJECTED`, `SUBMITTED`, `DEACTIVATED`, ... |
| `stage` | string | Comma-separated stages |
| `useable` | bool | `true` → only templates usable for sending (i.e. `APPROVED`) |
| `start_time` / `end_time` | int (epoch millis) | Time range filter |
| `element_name` | string | Filter by template name |
| `data` | string | Filter by template content/data |
| `page_no` / `page_size` | int | Pagination |

### Example

```bash
curl -G '{{BASE_URL}}/api/system/whatsapp/templates' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}' \
  --data-urlencode 'status=REJECTED' \
  --data-urlencode 'pageSize=20' \
  --data-urlencode 'pageNo=1'
```

### Response

```json
{
  "status": "success",
  "templates": [
    {
      "id": "00b8d1ed-7af6-4734-a7a1-e3062f21d7df",
      "elementName": "automation_template_2131081",
      "status": "REJECTED",
      "reason": "Invalid Format",
      "category": "UTILITY",
      "...": "..."
    }
  ]
}
```

`reason` is populated for rejected templates. Watch `containerMeta.correctCategory` if Meta has flagged a miscategorization.

---

## 3. Edit a template — `PUT /whatsapp/templates/{template_id}`

`template_id` is the Gupshup `id` field returned from Create/List (**not** the `elementName`).

All fields are optional — only the ones you send get updated. Sending none returns a `400`.

| Field | Notes |
|---|---|
| `content` | New body text |
| `template_type` | `TEXT`, `IMAGE`, `VIDEO`, `DOCUMENT` |
| `example` | New example text |
| `example_header` | New header example |
| `enable_sample` | bool |
| `header` | New header text |
| `footer` | New footer text |
| `buttons` | New buttons array |
| `example_media` | New `handleId` (⚠️ carousel templates with media **cannot** be updated) |
| `media_id` / `media_url` | Alternative ways to point at media |
| `category` | `AUTHENTICATION` \| `MARKETING` \| `UTILITY` |

### Example

```bash
curl -X PUT '{{BASE_URL}}/api/system/whatsapp/templates/5da48971-6181-4c45-8de0-c786a93328e7' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}' \
  -H 'Content-Type: application/json' \
  -d '{
    "content": "Your order {{1}} has shipped and will arrive by {{2}}.",
    "footer": "Track it anytime from the app"
  }'
```

### Response

```json
{ "success": true, "status": "success" }
```

### Errors
- `400` — no fields provided
- `502` — e.g. `"No Template found for given id"` if the `template_id` is wrong

---

## 4. Delete a template — `DELETE /whatsapp/templates/{element_name}`

Uses `elementName` (the human-readable template name), **not** the template id. This is **irreversible** — Gupshup does not support restoring a deleted template.

### Example

```bash
curl -X DELETE '{{BASE_URL}}/api/system/whatsapp/templates/order_confirmation' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}'
```

### Response

```json
{ "success": true, "status": "success" }
```

### Errors (all surfaced as `502` with Gupshup's message in `detail`)
- `"Template Does not exists."` — wrong/already-deleted elementName
- `"Delete Operation is not allowed for sandbox apps"` — app isn't live yet
- `"Template Cannot be deleted"` — not a master template
- `"Please Check If App Has been approved"` — app not approved

---

## 5. Upload sample media — `POST /whatsapp/templates/media`

Required before creating an `IMAGE`, `VIDEO`, `DOCUMENT`, or media-carousel template. Returns a `handleId` string to pass as `example_media` in [Create](#1-create-a-template--post-whatsapptemplates) or [Edit](#3-edit-a-template--put-whatsapptemplatestemplate_id).

This is a **multipart/form-data** request — either upload a real file, or point at a public URL. Provide exactly one of `file` / `file_url`.

| Field | Required | Notes |
|---|---|---|
| `file_type` | ✅ | **A MIME type** — `image/png`, `image/jpeg`, `video/mp4`, `application/pdf`, etc. ⚠️ A bare extension or category like `image`/`png` is silently accepted by this endpoint but produces a handleId that gets rejected later, at template-submission time, with `"The type of file is not supported"` — always use the full MIME type. |
| `file` | one of `file`/`file_url` | The actual file to upload |
| `file_url` | one of `file`/`file_url` | A public URL Gupshup can fetch instead of uploading bytes |

### Example — direct file upload

```bash
curl -X POST '{{BASE_URL}}/api/system/whatsapp/templates/media' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}' \
  -F 'file_type=image/jpeg' \
  -F 'file=@/path/to/banner.jpg'
```

### Example — from a URL

```bash
curl -X POST '{{BASE_URL}}/api/system/whatsapp/templates/media' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}' \
  -F 'file_type=image/png' \
  -F 'file_url=https://example.com/banner.jpg'
```

### Response

```json
{
  "success": true,
  "status": "success",
  "handleId": {
    "message": "4::aW1hZ2UvcadG5n:ARYaMMMA2QvIXuQZdPjWVXTOqfoBU3n0L1Ft..."
  }
}
```

Take `handleId.message` and pass it as `example_media` in the Create/Edit template request.

### Errors
- `400` — neither `file` nor `file_url` provided

---

## End-to-end flow: creating an image template

```bash
# 1. Upload the sample image, capture handleId.message from the response
curl -X POST '{{BASE_URL}}/api/system/whatsapp/templates/media' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}' \
  -F 'file_type=image/jpeg' \
  -F 'file=@banner.jpg'

# 2. Create the template using that handleId as example_media
curl -X POST '{{BASE_URL}}/api/system/whatsapp/templates' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}' \
  -H 'Content-Type: application/json' \
  -d '{
    "element_name": "promo_banner",
    "category": "MARKETING",
    "template_type": "IMAGE",
    "content": "Check out our sale {{1}}!",
    "example": "Check out our sale this weekend!",
    "example_media": "4::aW1hZ2UvcadG5n:ARYaMMMA2Qv...<handleId>"
  }'

# 3. Poll status until approved
curl -G '{{BASE_URL}}/api/system/whatsapp/templates' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}' \
  --data-urlencode 'elementName=promo_banner'
```

---

## 6. Trigger a campaign — `POST /whatsapp/campaigns`

Sends an **approved** template to many users at once. The request returns immediately with a `campaign_id`; the actual sending runs in the background.

### Fields

| Field | Required | Default | Notes |
|---|---|---|---|
| `name` | ✅ | — | A label for the campaign (shown in listings) |
| `template_id` | ✅ | — | The Gupshup `id` of an **APPROVED** template (get it from [List Templates](#2-list-templates--get-whatsapptemplates)) |
| `params` | optional | `[]` | Values that fill the template's variables — see below |
| `target` | optional | `"all"` | `"all"` = every user with a phone number · `"tiers"` = filter by engagement tier · `"numbers"` = manually entered phone numbers |
| `tiers` | required if `target="tiers"` | — | Any of: `daily`, `high`, `medium`, `low`, `inactive` |
| `numbers` | required if `target="numbers"` | — | List of phone numbers **with country code**, e.g. `["919876543210", "+91 88888 88888"]` — formatting/spaces/dashes are stripped automatically |
| `media_type` | required for media templates | — | `image` \| `video` \| `document` — must match the template's type |
| `media_url` | one of `media_url`/`media_id` when `media_type` is set | — | Public URL of the media to attach (e.g. a Cloudinary/R2 link) |
| `media_id` | one of `media_url`/`media_id` when `media_type` is set | — | Gupshup media id from a prior media upload |

### How template variables (`params`) work

If the approved template body is:

```
Hi! Our {{1}} sale is live — get {{2}} off until {{3}}.
```

then `params` supplies the values **in order** — `params[0]` fills `{{1}}`, `params[1]` fills `{{2}}`, and so on:

```json
{ "params": ["Monsoon", "50%", "July 20"] }
```

Every recipient gets: *"Hi! Our Monsoon sale is live — get 50% off until July 20."*

Rules & tips:

- **Count must match**: send exactly as many params as the template has `{{n}}` placeholders. A mismatch makes Gupshup reject the send (those recipients will show as `failed` in the stats).
- **WhatsApp formatting works inside params**: wrap a value in asterisks for bold — `"*Monsoon*"` renders as **Monsoon**. Same for `_italics_` and `~strikethrough~`.
- **Templates with no variables**: just omit `params` or send `[]`.

### Per-recipient personalization

Any param can instead be a **field reference**, which pulls a different value for each recipient from their `user_profile` document — e.g. filling `{{1}}` with each user's own name:

```json
{
  "params": [
    { "field": "username", "fallback": "there" },
    "50%"
  ]
}
```

`{{1}}` becomes each recipient's `username` (or `"there"` if they don't have one — e.g. a manually-entered number under `target: "numbers"` with no matching account); `{{2}}` is `"50%"` for everyone.

- **Allowed fields**: `username`, `email`, `phone`, `engagement_tier`, `trial_engagement_tier`, `engagement_status`, `subscription_status`. This is a fixed allowlist — anything else (e.g. `password`) is rejected with a `400`, since these values go straight into a WhatsApp message. Fetch the current list (with display labels, for building a dropdown) from `GET /whatsapp/campaigns/personalization-fields` — see below — instead of hardcoding it, so the frontend stays in sync if the allowlist changes.
- **`fallback`** (optional, defaults to `""`) is used whenever the field is missing or empty for that recipient.
- **Mixing is fine**: a `params` list can combine fixed strings and field references freely, in any order.
- **Resolved once, at trigger time**: each recipient's filled-in params are computed and stored when the campaign is created, not re-evaluated later — so if you edit a user's profile after triggering a campaign, an in-flight or already-sent message won't reflect the change.

#### Discovering available fields — `GET /whatsapp/campaigns/personalization-fields`

```bash
curl '{{BASE_URL}}/api/system/whatsapp/campaigns/personalization-fields' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}'
```

```json
{
  "fields": [
    { "field": "username", "label": "Name" },
    { "field": "email", "label": "Email" },
    { "field": "phone", "label": "Phone number" },
    { "field": "engagement_tier", "label": "Engagement tier (current)" },
    { "field": "trial_engagement_tier", "label": "Engagement tier (during trial)" },
    { "field": "engagement_status", "label": "Engagement status (cold/warm/hot/converted)" },
    { "field": "subscription_status", "label": "Subscription status" }
  ]
}
```

Use `field` as the value you send back in `{"field": "...", "fallback": "..."}`, and `label` as the human-readable option text in a dropdown.

### Audience selection

- `"target": "all"` — every user in `user_profile` with a non-empty phone number.
- `"target": "tiers", "tiers": ["high", "daily"]` — only users whose `engagement_tier` (computed by the segmentation scheduler over their last 30 days of activity) matches. Tiers: `daily` ≥20 active days, `high` 12–19, `medium` 6–11, `low` 1–5, `inactive` 0.
- `"target": "numbers", "numbers": [...]` — exactly the phone numbers you type in, whether or not they are app users. Numbers must include the country code (e.g. `91...` for India); spaces, dashes, `+` and other formatting are stripped automatically, duplicates are removed, and each number must be 8–15 digits or the whole request is rejected with a `400` listing the bad entries. Numbers that belong to known users get their email attached in the campaign's message records; unknown numbers are sent to anyway, with `email: null`.

### Example — engagement tiers

```bash
curl -X POST '{{BASE_URL}}/api/system/whatsapp/campaigns' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "July re-engagement",
    "template_id": "5da48971-6181-4c45-8de0-c786a93328e7",
    "params": ["*Monsoon*", "50%", "July 20"],
    "target": "tiers",
    "tiers": ["low", "inactive"]
  }'
```

### Example — manual list of numbers

```bash
curl -X POST '{{BASE_URL}}/api/system/whatsapp/campaigns' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "VIP preview blast",
    "template_id": "5da48971-6181-4c45-8de0-c786a93328e7",
    "params": ["*Monsoon*", "50%", "July 20"],
    "target": "numbers",
    "numbers": ["919876543210", "+91 88888 88888", "91-70000-00001"]
  }'
```

### Sending media templates (IMAGE / VIDEO / DOCUMENT)

If the approved template is a media template, the send must include the actual media alongside the params. The flow:

1. **Host the media** — upload the file anywhere publicly reachable (Cloudinary, R2, etc.) and take its URL, or use a Gupshup media id if you already have one from a media upload.
2. **Trigger the campaign** with `media_type` + `media_url` (or `media_id`):

```bash
curl -X POST '{{BASE_URL}}/api/system/whatsapp/campaigns' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Banner blast",
    "template_id": "d00cca5c-ec89-431f-9421-70952fcd5695",
    "params": ["*Monsoon*"],
    "target": "all",
    "media_type": "image",
    "media_url": "https://res.cloudinary.com/yourcloud/image/upload/banner.jpg"
  }'
```

Validation: `media_type` without a `media_url`/`media_id` (or vice versa) is rejected with a `400`. For plain TEXT templates just omit all three media fields.

> Note: the `handleId` from the [template media upload endpoint](#5-upload-sample-media--post-whatsapptemplatesmedia) is **only** for creating templates (the sample Meta reviews) — it is *not* a `media_id` for sending. For sending, use a public `media_url`.

### Response

```json
{ "success": true, "campaign_id": "6650f2...", "total_recipients": 142 }
```

### Errors
- `400` — invalid/empty `tiers`, invalid/empty `numbers` (bad entries are listed in the error), or no users match the audience
- `500` — Gupshup env vars not configured

---

## 7. Campaign stats — `GET /whatsapp/campaigns` and `GET /whatsapp/campaigns/{campaign_id}`

```bash
# All campaigns, newest first
curl '{{BASE_URL}}/api/system/whatsapp/campaigns' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}'

# One campaign
curl '{{BASE_URL}}/api/system/whatsapp/campaigns/6650f2...' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}'
```

### Response (detail)

```json
{
  "id": "6650f2...",
  "name": "July re-engagement",
  "template_id": "5da48971-...",
  "params": ["*Monsoon*", "50%", "July 20"],
  "target": "tiers",
  "tiers": ["low", "inactive"],
  "total_recipients": 142,
  "status": "completed",
  "created_at": 1752105600,
  "completed_at": 1752105745,
  "stats": {
    "pending": 0,
    "sent": 130,
    "delivered": 118,
    "read": 74,
    "failed": 12
  }
}
```

### What the stats mean

| Stat | Meaning |
|---|---|
| `pending` | Not attempted yet (campaign still running) |
| `sent` | Accepted by Gupshup, no delivery receipt yet |
| `delivered` | Reached the user's phone |
| `read` | The user opened/saw the message |
| `failed` | Send rejected by Gupshup, or delivery failed (blocked number, opted out, etc.) |

A message moves forward only: `pending → sent → delivered → read` (or `failed`). `delivered`/`read` include everything before them — a `read` message was obviously also delivered — so **total = pending + sent + delivered + read + failed**.

---

## 8. Per-contact breakdown — `GET /whatsapp/campaigns/{campaign_id}/contacts`

The stats above are aggregate counts. This route lists the individual recipients — who received it, who read it, who failed and why.

### Query params (all optional)

| Param | Notes |
|---|---|
| `status` | Filter to one status: `pending`, `sent`, `delivered`, `read`, `failed` |
| `page_no` | Default `1` |
| `page_size` | Default `50`, max `200` |

### Example

```bash
curl -G '{{BASE_URL}}/api/system/whatsapp/campaigns/6650f2.../contacts' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}' \
  --data-urlencode 'status=failed' \
  --data-urlencode 'page_size=100'
```

### Response

```json
{
  "total": 142,
  "page_no": 1,
  "page_size": 50,
  "contacts": [
    {
      "email": "jane@example.com",
      "phone": "919876543210",
      "params": ["*Monsoon*", "Jane"],
      "status": "read",
      "error": null,
      "updated_at": 1752105745
    },
    {
      "email": null,
      "phone": "917000000001",
      "params": ["*Monsoon*", "there"],
      "status": "failed",
      "error": "Gupshup send failed (400): Invalid Destination",
      "updated_at": 1752105746
    }
  ]
}
```

- `email` is `null` for manually-entered numbers (`target: "numbers"`) with no matching user account.
- `params` shows the fully-resolved values actually sent to that recipient — useful for confirming personalization worked (e.g. seeing each person's real name instead of the `{"field": ...}` spec).
- `error` is populated only for `failed` contacts — either a Gupshup rejection at send time, or a `failed` delivery event from the webhook.
- `status` here already merges Gupshup's internal `submitted`/`sent` distinction into a single `sent`, matching the aggregate stats.

### Errors
- `400` — invalid campaign id, or invalid `status` value
- `404` — campaign not found

---

## 9. Delivery-event webhook — `POST /api/whatsapp/webhook` ⚠️ setup required

`delivered` and `read` counts come from Gupshup **message-event callbacks**. This endpoint (public, no auth, always returns 200) receives them and updates the campaign stats.

**One-time setup:** in the Gupshup dashboard (or via their Set Callback URL API), set your app's callback URL to:

```
https://<your-domain>/api/whatsapp/webhook
```

and make sure message events (sent / delivered / read / failed) are enabled. Until this is configured, campaigns will only ever show `sent` and `failed` (known at send time) — `delivered` and `read` will stay at 0.

Events for non-campaign messages (e.g. login OTPs) hit the same endpoint and are safely ignored.

---

## End-to-end flow: template → campaign → stats

```bash
# 1. Create the template (see section 1) and wait until APPROVED (section 2)

# 2. Grab the template id
curl -G '{{BASE_URL}}/api/system/whatsapp/templates' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}' \
  --data-urlencode 'elementName=monsoon_sale' \
# → templates[0].id = "5da48971-..."

# 3. Fire the campaign
curl -X POST '{{BASE_URL}}/api/system/whatsapp/campaigns' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}' \
  -H 'Content-Type: application/json' \
  -d '{ "name": "Monsoon blast", "template_id": "5da48971-...", "params": ["*Monsoon*", "50%"], "target": "all" }'
# → campaign_id = "6650f2..."

# 4. Watch the numbers roll in
curl '{{BASE_URL}}/api/system/whatsapp/campaigns/6650f2...' \
  -H 'Authorization: Bearer {{ADMIN_TOKEN}}'
```

---

## Notes & gotchas

- **Single WABA**: these routes always act on the Gupshup app configured via `GUPSHUP_APP_ID`/`GUPSHUP_TOKEN` — there's no multi-app/multi-tenant support here.
- **`template_id` vs `elementName`**: Edit needs the Gupshup-generated `id` (from Create/List responses); Delete needs the human-readable `elementName` you chose. Mixing these up returns a `502` from Gupshup, not a clean validation error.
- **Approval is async**: a successful `201` from Create just means Gupshup *accepted* the submission — actual Meta approval/rejection happens later and must be checked via List.
- **Category miscategorization**: since June 2024, Meta may auto-flag/auto-correct a template's category. Check `containerMeta.correctCategory` and `oldCategory` fields in List responses.
- **Carousel + media**: carousel templates with media cannot be edited after creation (Gupshup limitation).
- **Rate limit**: Gupshup allows 10 requests/minute on template APIs — expect `429` if the dashboard batches too many calls.
