# Notifications

## Architecture

Every notification has two delivery paths:

- **Real-time (online users):** pushed over the SSE stream at `GET /api/user/events`
- **Persistent (offline users):** stored in MongoDB `notifications` collection, fetched via `GET /api/user/notifications` when the user opens the app

On login: connect to SSE + call `GET /api/user/notifications` once. HTTP for history, SSE for live updates.

---

## SSE Stream

```
GET /api/user/events
Authorization: Bearer <token>
```

Connect once after login, keep open. Reconnect on disconnect.

```js
const es = new EventSource("/api/user/events", { headers: { Authorization: `Bearer ${token}` } });
es.onmessage = (e) => {
  const event = JSON.parse(e.data);
  // Every event: { type, title, body, data }
  switch (event.type) {
    case "new_masterclass":     // new masterclass published
    case "new_resource":        // new resource uploaded
    case "system_announcement": // admin broadcast
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

---

## All Event Types

| type | Stored in DB | `data` fields |
|---|---|---|
| `new_masterclass` | Yes | `{}` |
| `new_resource` | Yes | `{ resource_id, category }` |
| `system_announcement` | Yes | `{}` |
| `guided_viz_complete` | No | `{ session_id, audio_url }` |
| `guided_viz_error` | No | `{ session_id }` |
| `eft_complete` | No | `{ session_id, audio_url }` |

`guided_viz_*` and `eft_complete` are ephemeral — not stored in DB. All others are persistent and fetchable via the notifications endpoints.

> **Unknown types:** Admin can send custom types at any time. Always implement a `default` case that displays `title` and `body` as a generic notification — the shape is always the same so it will render correctly without any code change.

```js
switch (event.type) {
  case "guided_viz_complete":
    // navigate to audio player
    break;
  case "eft_complete":
    // navigate to audio player
    break;
  default:
    // show title + body as a generic notification toast
    // also display event.type as a tag/chip on the notification card
}
```

---

## Examples

```json
{ "type": "new_masterclass", "title": "New Masterclass Available", "body": "Letting Go of What No Longer Serves You — available now.", "data": {} }

{ "type": "new_resource", "title": "New Audio Available", "body": "Morning Abundance Meditation — A 10-minute morning meditation.", "data": { "resource_id": "uuid", "category": "audio" } }

{ "type": "guided_viz_complete", "title": "Your visualization is ready", "body": "Tap to listen.", "data": { "session_id": "uuid", "audio_url": "https://..." } }

{ "type": "guided_viz_error", "title": "Visualization failed", "body": "Could not generate your visualization. Please try again.", "data": { "session_id": "uuid" } }

{ "type": "eft_complete", "title": "Your tapping session is ready", "body": "Tap to listen.", "data": { "session_id": "uuid", "audio_url": "https://..." } }
```

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
