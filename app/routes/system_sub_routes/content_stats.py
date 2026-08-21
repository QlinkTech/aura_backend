import time
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from bson import ObjectId
from bson.errors import InvalidId
from app.services.db.mongo_utils import activity_log, resources, user_profile
from app.utils.logger_config import logger

content_stats_router = APIRouter()

# Only events that name a specific piece of content. The bare "resource_list_view"
# event (library tab opened) is deliberately excluded — it says nothing about
# which content anyone consumed.
_VIEW_MATCH = {"type": "resource_view", "ref_id": {"$nin": [None, ""]}}


def _resource_index(ids: list) -> dict:
    """id string -> {name, category, type} for the resources named in a result set."""
    object_ids = []
    for rid in ids:
        try:
            object_ids.append(ObjectId(rid))
        except (InvalidId, TypeError):
            continue
    return {
        str(doc["_id"]): {
            "name":     doc.get("name", ""),
            "category": doc.get("category", ""),
            "type":     doc.get("type", ""),
        }
        for doc in resources.find({"_id": {"$in": object_ids}}, {"name": 1, "category": 1, "type": 1})
    }


def _names_for(emails: list) -> dict:
    return {
        doc["email"]: doc.get("username", "")
        for doc in user_profile.find({"email": {"$in": emails}}, {"_id": 0, "email": 1, "username": 1})
    }


def _granted_access_emails() -> list:
    """Emails of comped (manually granted) users — same set /stats parks aside."""
    return [
        doc["email"]
        for doc in user_profile.find({"is_bypassed": True}, {"_id": 0, "email": 1})
        if doc.get("email")
    ]


@content_stats_router.get("/content-stats")
def content_stats(
    category: str = Query(None, description="Filter to one category, e.g. masterclass_vault"),
    days: int = Query(None, ge=1, description="Only count views from the last N days; omit for all time"),
    include_unopened: bool = Query(True, description="Include content nobody has opened yet"),
    include_granted_access: bool = Query(
        False,
        description=(
            "Include views by comped (manually granted) users. Default false, "
            "matching /stats, so open counts reflect real customers only."
        ),
    ),
):
    """Every piece of content, with how many people opened it and when."""
    try:
        match = dict(_VIEW_MATCH)
        if days:
            match["created_at"] = {"$gte": int(time.time()) - days * 24 * 60 * 60}
        if not include_granted_access:
            # Comped users never had to convert, so their reading habits aren't
            # customer behaviour — drop their events before anything is counted.
            match["email"] = {"$nin": _granted_access_emails()}

        rows = list(activity_log.aggregate([
            {"$match": match},
            {"$group": {
                "_id":          "$ref_id",
                "opens":        {"$sum": 1},
                "viewers":      {"$addToSet": "$email"},
                "first_opened": {"$min": "$created_at"},
                "last_opened":  {"$max": "$created_at"},
            }},
        ]))

        meta = _resource_index([r["_id"] for r in rows])

        content = []
        for r in rows:
            info = meta.get(r["_id"])
            if info is None:
                # Viewed content that has since been deleted — kept visible rather
                # than dropped, so the view history stays honest.
                info = {"name": "(deleted resource)", "category": "", "type": ""}
            if category and info["category"] != category:
                continue
            content.append({
                "resource_id":  r["_id"],
                **info,
                "opens":        r["opens"],
                "unique_viewers": len(r["viewers"]),
                "first_opened": r["first_opened"],
                "last_opened":  r["last_opened"],
            })

        if include_unopened:
            seen = {c["resource_id"] for c in content}
            unopened_query = {"category": category} if category else {}
            for doc in resources.find(unopened_query, {"name": 1, "category": 1, "type": 1}):
                rid = str(doc["_id"])
                if rid in seen:
                    continue
                content.append({
                    "resource_id":  rid,
                    "name":         doc.get("name", ""),
                    "category":     doc.get("category", ""),
                    "type":         doc.get("type", ""),
                    "opens":        0,
                    "unique_viewers": 0,
                    "first_opened": None,
                    "last_opened":  None,
                })

        content.sort(key=lambda c: (c["opens"], c["unique_viewers"]), reverse=True)

        return {
            "window_days":     days,
            "include_granted_access": include_granted_access,
            "total_opens":     sum(c["opens"] for c in content),
            "content_count":   len(content),
            "never_opened":    sum(1 for c in content if c["opens"] == 0),
            "content":         content,
        }

    except Exception as e:
        logger.error("System: error fetching content stats", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@content_stats_router.get("/content-stats/viewers")
def content_viewers(
    resource_id: str = Query(..., description="Which piece of content to expand"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    include_granted_access: bool = Query(
        False,
        description="Same meaning as on /content-stats — keep it identical to the table's current scope.",
    ),
):
    """Who opened this piece of content, and when."""
    try:
        match = {**_VIEW_MATCH, "ref_id": resource_id}
        if not include_granted_access:
            match["email"] = {"$nin": _granted_access_emails()}

        rows = list(activity_log.aggregate([
            {"$match": match},
            {"$group": {
                "_id":         "$email",
                "opens":       {"$sum": 1},
                "first_opened": {"$min": "$created_at"},
                "last_opened": {"$max": "$created_at"},
            }},
            {"$sort": {"last_opened": -1}},
        ]))

        names = _names_for([r["_id"] for r in rows])
        meta  = _resource_index([resource_id]).get(resource_id, {})
        skip  = (page - 1) * limit

        return {
            "resource_id": resource_id,
            "name":        meta.get("name", "(deleted resource)"),
            "category":    meta.get("category", ""),
            "include_granted_access": include_granted_access,
            "total_opens": sum(r["opens"] for r in rows),
            "total":       len(rows),
            "page":        page,
            "limit":       limit,
            "viewers": [
                {
                    "email":        r["_id"],
                    "username":     names.get(r["_id"], ""),
                    "opens":        r["opens"],
                    "first_opened": r["first_opened"],
                    "last_opened":  r["last_opened"],
                }
                for r in rows[skip: skip + limit]
            ],
        }

    except Exception as e:
        logger.error("System: error fetching content viewers", extra={"id": resource_id, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@content_stats_router.get("/content-stats/user")
def user_content_history(
    email: str = Query(..., description="Whose history to return"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    """Everything this user has opened, newest first — one row per open."""
    try:
        email = email.lower()
        query = {**_VIEW_MATCH, "email": email}
        total = activity_log.count_documents(query)

        events = list(
            activity_log.find(query, {"_id": 0, "ref_id": 1, "created_at": 1})
            .sort("created_at", -1)
            .skip((page - 1) * limit)
            .limit(limit)
        )
        meta = _resource_index([e["ref_id"] for e in events])
        profile = user_profile.find_one({"email": email}, {"_id": 0, "username": 1})

        return {
            "email":    email,
            "username": profile.get("username", "") if profile else "",
            "total_opens": total,
            "distinct_content": len(activity_log.distinct("ref_id", query)),
            "page":     page,
            "limit":    limit,
            "history": [
                {
                    "resource_id": e["ref_id"],
                    "opened_at":   e["created_at"],
                    **meta.get(e["ref_id"], {"name": "(deleted resource)", "category": "", "type": ""}),
                }
                for e in events
            ],
        }

    except Exception as e:
        logger.error("System: error fetching user content history", extra={"email": email, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)
