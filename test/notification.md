# Notifications

## Architecture

Every notification has two delivery paths:

- **Real-time (online users):** pushed over the SSE stream at `GET /api/user/events`
- **Persistent (offline users):** stored in MongoDB `notifications` collection, fetched via `GET /api/user/notifications` when the user opens the app

---

## SSE Stream

```
GET /api/user/events
Authorization: Bearer <token>
```

Frontend connects once after login and keeps the stream open. All event types arrive here.

```js
const es = new EventSource("/api/user/events", { headers: { Authorization: `Bearer ${token}` } });
es.onmessage = (e) => {
  const event = JSON.parse(e.data);
  // Every event: { type, title, body, data }
  switch (event.type) {
    case "new_masterclass":     // admin-sent push
    case "system_announcement": // admin-sent push
    case "guided_viz_complete": // guided viz audio ready
    case "guided_viz_error":    // guided viz failed
    case "eft_complete":        // eft tapping audio ready
  }
};
```

---

## Unified Event Shape

Every SSE event follows the same envelope — no exceptions.

```json
{
  "type": "...",
  "title": "...",
  "body": "...",
  "data": {}
}
```

| Field | Description |
|---|---|
| `type` | Identifies the event (see table below) |
| `title` | Short human-readable label |
| `body` | Detail text |
| `data` | Payload — fields vary by type (see below) |

---

## All Event Types

| type | Triggered by | Stored in DB | `data` fields |
|---|---|---|---|
| `new_masterclass` | Admin dashboard (manual send) | Yes | `{ masterclass_id }` |
| `system_announcement` | Admin dashboard (manual send) | Yes | `{}` |
| `new_resource` | Auto — on resource upload | Yes | `{ resource_id, category }` |
| `guided_viz_complete` | Guided viz background task | No | `{ session_id, audio_url }` |
| `guided_viz_error` | Guided viz background task | No | `{ session_id }` |
| `eft_complete` | EFT tapping session | No | `{ session_id, audio_url }` |

Add new admin `type` values freely — no code change needed, just pass a new string when calling the send endpoint.

---

### Examples

```json
{ "type": "new_masterclass", "title": "New Masterclass Available", "body": "Letting Go of What No Longer Serves You — available now.", "data": { "masterclass_id": "abc123" } }

{ "type": "guided_viz_complete", "title": "Your visualization is ready", "body": "Tap to listen.", "data": { "session_id": "uuid", "audio_url": "https://..." } }

{ "type": "guided_viz_error", "title": "Visualization failed", "body": "Could not generate your visualization. Please try again.", "data": { "session_id": "uuid" } }

{ "type": "eft_complete", "title": "Your tapping session is ready", "body": "Tap to listen.", "data": { "session_id": "uuid", "audio_url": "https://..." } }
```

---

## Admin Endpoints

All require system JWT.

### Send Notification
```
POST /api/system/notifications/send
```

| Field | Type | Description |
|---|---|---|
| `target` | string | `"all"` for broadcast, or a specific user email |
| `type` | string | `notif_type` value (e.g. `"new_masterclass"`) |
| `title` | string | Notification title |
| `body` | string | Notification body text |
| `data` | object | Optional payload (e.g. `{ "masterclass_id": "..." }`) |

Response:
```json
{ "success": true, "delivered_to": 142 }
```

`delivered_to` is the number of DB records written (= number of users targeted). Online users also receive the SSE push instantly.

---

## User Endpoints

All require user JWT.

### List Notifications
```
GET /api/user/notifications
```
Returns all notifications (newest first) with unread count.

```json
{
  "notifications": [
    {
      "notification_id": "uuid",
      "type": "new_masterclass",
      "title": "New Masterclass Available",
      "body": "...",
      "data": {},
      "is_read": false,
      "created_at": 1715000000
    }
  ],
  "unread_count": 3
}
```

### Unread Badge Count
```
GET /api/user/notifications/unread-count
```
```json
{ "unread_count": 3 }
```

### Mark One Read
```
POST /api/user/notifications/{notification_id}/read
```

### Mark All Read
```
POST /api/user/notifications/read-all
```
```json
{ "success": true, "marked_read": 3 }
```
