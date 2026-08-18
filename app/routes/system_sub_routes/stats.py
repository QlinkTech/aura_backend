import time
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from app.services.db.mongo_utils import (
    user_profile, chat_sessions, eft_sessions,
    guided_viz_sessions, journal_log, activity_log, resources, notifications,
    payments,
)
from app.utils.logger_config import logger

stats_router = APIRouter()

# "This month" follows the IST calendar — the business's local month, not UTC's.
# Fixed offset rather than ZoneInfo("Asia/Kolkata"): India has no DST, and the
# slim runtime image ships no tzdata (same reasoning as gupshup/notifications.py).
_IST = timezone(timedelta(hours=5, minutes=30))

DAY = 24 * 60 * 60

# Razorpay statuses that mean the subscription is live and billing.
_PAYING_STATUSES = {"active", "authenticated", "charged"}
# Wider than the above on purpose: this is a "did money EVER change hands" test,
# so it has to stay true after the subscription ends.
_EVER_PAID_STATUSES = _PAYING_STATUSES | {"completed"}

# Every collection that counts as the user "showing up".
ACTIVITY_COLLECTIONS = [chat_sessions, eft_sessions, guided_viz_sessions, journal_log, activity_log]


def _pct(part: int, whole: int, decimals: int = 1) -> float:
    return round(part * 100 / whole, decimals) if whole else 0


def _avg(total: int, count: int, decimals: int = 2) -> float:
    return round(total / count, decimals) if count else 0


def _rupees(paise: int) -> float:
    """Razorpay reports every amount in paise; the dashboard talks in rupees."""
    return round((paise or 0) / 100, 2)


def _month_start_ts() -> int:
    """Epoch seconds at 00:00 IST on the 1st of the current month."""
    now_ist = datetime.now(_IST)
    return int(now_ist.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())


def _lifecycle_stage(doc: dict, now: int) -> str:
    """Where this user sits in the funnel, as one exclusive answer.

    Checked in priority order so every counted user lands in exactly one stage
    and the stages always sum to `counted_users`. Comped access is deliberately
    NOT a stage here — it's an access grant, not a funnel position, and it's
    reported separately as overview.comped_access.
    """
    sub_status = doc.get("subscription_status")
    paid_until = doc.get("paid_until") or 0
    trial_end  = doc.get("trial_end_at") or 0
    ever_paid  = bool(paid_until) or sub_status in _EVER_PAID_STATUSES

    if sub_status in _PAYING_STATUSES:
        return "paying"
    if ever_paid:
        # Paid before, not billing now. Still inside the window they already
        # paid for = winding down; past it = actually churned.
        return "winding_down" if paid_until and now < paid_until else "churned"
    if trial_end:
        return "trial_active" if now < trial_end else "trial_expired"
    if doc.get("early_bird_sub_id"):
        # Started a Razorpay checkout that never completed.
        return "checkout_abandoned"
    return "signed_up_only"


# Fields returned for each user in a drill-down list. Enough to identify and
# act on someone without a second request; never the password hash.
_USER_CARD = {
    "_id": 0, "email": 1, "username": 1, "phone": 1, "is_paid": 1, "is_bypassed": 1,
    "subscription_status": 1, "early_bird_sub_id": 1, "early_bird_plan_key": 1, "trial_end_at": 1,
    "paid_until": 1, "created_at": 1, "engagement_status": 1, "vision_board_url": 1,
}


def _active_user_sets(now: int, excluded: set) -> tuple:
    """Emails seen in the last 7 and 30 days across every activity surface."""
    cutoff_30, cutoff_7 = now - 30 * DAY, now - 7 * DAY
    active_30, active_7 = set(), set()

    for col in ACTIVITY_COLLECTIONS:
        for doc in col.aggregate([
            {"$match": {"created_at": {"$gte": cutoff_30}}},
            {"$group": {"_id": "$email", "last_seen": {"$max": "$created_at"}}},
        ]):
            email = doc["_id"]
            if not email or email in excluded:
                continue
            active_30.add(email)
            if doc["last_seen"] >= cutoff_7:
                active_7.add(email)

    return active_7, active_30


def _feature_usage(collection, scope: list, extra_counts: dict = None) -> dict:
    """Sessions, distinct users and per-user average for a session collection."""
    agg = list(collection.aggregate(scope + [
        {"$group": {"_id": "$email", "session_count": {"$sum": 1}}},
        {"$group": {
            "_id": None,
            "users":        {"$sum": 1},
            "sessions":     {"$sum": "$session_count"},
            "avg_per_user": {"$avg": "$session_count"},
        }},
    ]))
    agg = agg[0] if agg else {}
    return {
        "users":        agg.get("users", 0),
        "sessions":     agg.get("sessions", 0),
        "avg_per_user": round(agg.get("avg_per_user", 0), 2),
        **(extra_counts or {}),
    }


@stats_router.get("/stats")
def get_stats(
    include_granted_access: bool = Query(
        False,
        description=(
            "Include comped (manually granted) users in every metric. "
            "Default false: they are excluded everywhere except total_users and "
            "comped_access, so the numbers reflect real customers only."
        ),
    ),
):
    try:
        now         = int(time.time())
        month_start = _month_start_ts()

        # ── One pass over user profiles ──────────────────────────
        # Funnel stage, engagement temperature and vision-board state all live
        # on the profile doc, so they come out of a single read rather than a
        # dozen count_documents() round trips.
        total_users = counted_users = comped_access = new_this_month = 0
        ever_trialed = ever_paid_users = trialed_and_paid = 0
        trials_ending_soon = payment_halted = 0
        excluded_emails = set()
        counted_emails = set()
        plan_mix   = {}
        # Emails behind each needs_attention row, gathered in the same pass that
        # counts them so the list can never disagree with the number.
        attention: dict = {k: set() for k in (
            "trials_ending_in_7_days", "payment_halted", "winding_down",
            "vision_boards_failed", "vision_boards_stuck",
        )}
        lifecycle  = {}
        engagement = {}
        vision     = {"generated": 0, "preparing": 0, "failed": 0, "not_started": 0}

        for doc in user_profile.find({}, {
            "email": 1, "is_paid": 1, "is_bypassed": 1, "subscription_status": 1,
            "early_bird_sub_id": 1, "early_bird_plan_key": 1, "trial_end_at": 1,
            "paid_until": 1, "created_at": 1, "engagement_status": 1, "vision_board_url": 1,
        }):
            total_users += 1

            if doc.get("is_bypassed"):
                comped_access += 1
                if not include_granted_access:
                    # Comped users skew every rate — they never had to convert
                    # and their usage isn't customer behaviour. Park their email
                    # so the feature aggregations below drop them too.
                    if doc.get("email"):
                        excluded_emails.add(doc["email"])
                    continue

            counted_users += 1
            if doc.get("email"):
                counted_emails.add(doc["email"])

            stage = _lifecycle_stage(doc, now)
            lifecycle[stage] = lifecycle.get(stage, 0) + 1
            email = doc.get("email")
            if stage == "winding_down" and email:
                attention["winding_down"].add(email)

            temp = doc.get("engagement_status") or "unclassified"
            engagement[temp] = engagement.get(temp, 0) + 1

            if (doc.get("created_at") or 0) >= month_start:
                new_this_month += 1

            sub_status = doc.get("subscription_status")
            trial_end  = doc.get("trial_end_at") or 0
            paid       = bool(doc.get("paid_until")) or sub_status in _EVER_PAID_STATUSES

            if trial_end:
                ever_trialed += 1
                if now < trial_end <= now + 7 * DAY:
                    trials_ending_soon += 1
                    if email:
                        attention["trials_ending_in_7_days"].add(email)
            if paid:
                ever_paid_users += 1
                if trial_end:
                    trialed_and_paid += 1
            if sub_status == "halted":
                payment_halted += 1
                if email:
                    attention["payment_halted"].add(email)

            plan_key = doc.get("early_bird_plan_key")
            if plan_key:
                plan_mix[plan_key] = plan_mix.get(plan_key, 0) + 1

            # Vision boards live on the profile as `vision_board_url`, which
            # doubles as the status field: "" / missing = never started,
            # "preparing" = queued, "failed" = errored, else a Cloudinary URL.
            url = doc.get("vision_board_url") or ""
            if url == "":
                vision["not_started"] += 1
            elif url in ("preparing", "failed"):
                vision[url] += 1
                if email:
                    attention["vision_boards_" + ("failed" if url == "failed" else "stuck")].add(email)
            else:
                vision["generated"] += 1

        active_7, active_30 = _active_user_sets(now, excluded_emails)

        # Feature numbers are restricted to emails that still have a profile, not
        # merely "not comped". Session collections can hold rows for accounts that
        # no longer exist, and counting those would make adoption disagree with
        # the /stats/segment list behind the same number.
        user_filter = {"email": {"$in": list(counted_emails)}}
        scope = [{"$match": user_filter}]

        # Money is scoped differently on purpose: revenue counts every rupee
        # actually received, even from an account that has since been removed.
        scope_filter = {"email": {"$nin": list(excluded_emails)}} if excluded_emails else {}

        # ── Feature usage ────────────────────────────────────────
        chat = _feature_usage(chat_sessions, scope)
        chat_msgs = list(chat_sessions.aggregate(scope + [
            {"$group": {"_id": None, "total": {"$sum": {"$size": {"$ifNull": ["$messages", []]}}}}},
        ]))
        chat["messages"] = chat_msgs[0]["total"] if chat_msgs else 0
        chat["avg_messages_per_session"] = _avg(chat["messages"], chat["sessions"])

        top = list(chat_sessions.aggregate(scope + [
            {"$project": {"email": 1, "msg_count": {"$size": {"$ifNull": ["$messages", []]}}}},
            {"$group": {"_id": "$email", "total_messages": {"$sum": "$msg_count"}, "session_count": {"$sum": 1}}},
            {"$sort": {"total_messages": -1}},
            {"$limit": 1},
        ]))
        chat["most_active_user"] = None
        if top:
            profile = user_profile.find_one({"email": top[0]["_id"]}, {"_id": 0, "username": 1})
            chat["most_active_user"] = {
                "email":          top[0]["_id"],
                "username":       profile.get("username", "") if profile else "",
                "total_messages": top[0]["total_messages"],
                "session_count":  top[0]["session_count"],
            }

        completed_eft = eft_sessions.count_documents({**user_filter, "is_complete": True})
        eft = _feature_usage(eft_sessions, scope, {"completed": completed_eft})
        eft["completion_rate_%"] = _pct(completed_eft, eft["sessions"])

        completed_gv = guided_viz_sessions.count_documents({**user_filter, "is_complete": True})
        errored_gv   = guided_viz_sessions.count_documents({**user_filter, "error": True})
        gv = _feature_usage(guided_viz_sessions, scope, {"completed": completed_gv, "errored": errored_gv})
        gv["completion_rate_%"] = _pct(completed_gv, gv["sessions"])

        journal = _feature_usage(journal_log, scope)
        journal["entries"] = journal.pop("sessions")
        journal["avg_entries_per_user"] = journal.pop("avg_per_user")

        # Vision boards are one-per-user (regenerating overwrites the same
        # Cloudinary object), so "users" and "boards made" are the same number.
        vision_users = vision["generated"]

        features = {
            "chat": {
                "users":                    chat["users"],
                "adoption_%":               _pct(chat["users"], counted_users),
                "sessions":                 chat["sessions"],
                "messages":                 chat["messages"],
                "avg_sessions_per_user":    chat["avg_per_user"],
                "avg_messages_per_session": chat["avg_messages_per_session"],
                "most_active_user":         chat["most_active_user"],
            },
            "eft_tapping": {
                "users":                 eft["users"],
                "adoption_%":            _pct(eft["users"], counted_users),
                "sessions":              eft["sessions"],
                "completed":             eft["completed"],
                "completion_rate_%":     eft["completion_rate_%"],
                "avg_sessions_per_user": eft["avg_per_user"],
            },
            "guided_visualization": {
                "users":                 gv["users"],
                "adoption_%":            _pct(gv["users"], counted_users),
                "sessions":              gv["sessions"],
                "completed":             gv["completed"],
                "errored":               gv["errored"],
                "completion_rate_%":     gv["completion_rate_%"],
                "avg_sessions_per_user": gv["avg_per_user"],
            },
            "vision_board": {
                "users":          vision_users,
                "adoption_%":     _pct(vision_users, counted_users),
                "boards_made":    vision_users,
                "preparing":      vision["preparing"],
                "failed":         vision["failed"],
                "success_rate_%": _pct(vision_users, vision_users + vision["failed"]),
            },
            "journal": {
                "users":                journal["users"],
                "adoption_%":           _pct(journal["users"], counted_users),
                "entries":              journal["entries"],
                "avg_entries_per_user": journal["avg_entries_per_user"],
            },
        }

        # ── Attention lists ──────────────────────────────────────
        # Each row carries the people behind it, so the admin can act without a
        # second lookup. Guided-viz errors are session-level, so their emails
        # come from the session collection rather than the profile pass.
        attention["guided_viz_errors"] = {
            e for e in guided_viz_sessions.distinct("email", {**user_filter, "error": True}) if e
        }

        attention_emails = set().union(*attention.values()) if attention else set()
        attention_cards = {
            doc["email"]: doc
            for doc in user_profile.find({"email": {"$in": list(attention_emails)}}, _USER_CARD)
            if doc.get("email")
        }

        def _attention_row(key: str, count: int) -> dict:
            """Count plus the users behind it, newest signup first, capped at 50."""
            emails = sorted(
                attention[key],
                key=lambda e: attention_cards.get(e, {}).get("created_at") or 0,
                reverse=True,
            )
            return {
                "count": count,
                "users": [attention_cards[e] for e in emails[:50] if e in attention_cards],
            }

        # ── Payments ─────────────────────────────────────────────
        # The payments collection holds two different record types: real money
        # events (event="payment.captured"/"payment.failed", carrying an amount
        # in paise) and subscription lifecycle events (no amount at all). Only
        # money events are counted here — mixing the two is what made the old
        # status breakdowns unreadable.
        captured_match = {**scope_filter, "event": "payment.captured"}
        failed_match   = {**scope_filter, "event": "payment.failed"}

        money = list(payments.aggregate([
            {"$match": captured_match},
            {"$group": {
                "_id": None,
                "count":      {"$sum": 1},
                "total":      {"$sum": "$amount"},
                "this_month": {"$sum": {"$cond": [{"$gte": ["$created_at", month_start]}, "$amount", 0]}},
            }},
        ]))
        money = money[0] if money else {}
        captured_count = money.get("count", 0)
        failed_count   = payments.count_documents(failed_match)

        # ── Content ──────────────────────────────────────────────
        resources_by_category = {
            doc["_id"]: doc["count"]
            for doc in resources.aggregate([{"$group": {"_id": "$category", "count": {"$sum": 1}}}])
        }
        total_notifs = notifications.count_documents({})
        total_unread = notifications.count_documents({"is_read": False})

        return {
            "scope": {
                "include_granted_access": include_granted_access,
                "total_users":            total_users,
                "counted_users":          counted_users,
                "excluded_users":         total_users - counted_users,
            },
            "overview": {
                "total_users":        total_users,
                "counted_users":      counted_users,
                "new_this_month":     new_this_month,
                "paying_customers":   lifecycle.get("paying", 0),
                "on_free_trial":      lifecycle.get("trial_active", 0),
                "comped_access":      comped_access,
                "active_last_7_days":  len(active_7),
                "active_last_30_days": len(active_30),
                # Counted but hasn't opened anything in a month — the churn pool.
                "dormant":            max(counted_users - len(active_30), 0),
                "lifetime_paying_customers": ever_paid_users,
                "trial_start_rate_%": _pct(ever_trialed, counted_users),
                "trial_to_paid_%":    _pct(trialed_and_paid, ever_trialed),
            },
            # Exclusive stages — these always add up to counted_users.
            "lifecycle": {
                "signed_up_only":     lifecycle.get("signed_up_only", 0),
                "checkout_abandoned": lifecycle.get("checkout_abandoned", 0),
                "trial_active":       lifecycle.get("trial_active", 0),
                "trial_expired":      lifecycle.get("trial_expired", 0),
                "paying":             lifecycle.get("paying", 0),
                "winding_down":       lifecycle.get("winding_down", 0),
                "churned":            lifecycle.get("churned", 0),
            },
            "engagement": engagement,
            "needs_attention": {
                "trials_ending_in_7_days": _attention_row("trials_ending_in_7_days", trials_ending_soon),
                "payment_halted":          _attention_row("payment_halted", payment_halted),
                "winding_down":            _attention_row("winding_down", lifecycle.get("winding_down", 0)),
                "vision_boards_failed":    _attention_row("vision_boards_failed", vision["failed"]),
                "vision_boards_stuck":     _attention_row("vision_boards_stuck", vision["preparing"]),
                "guided_viz_errors":       _attention_row("guided_viz_errors", errored_gv),
            },
            "features": features,
            "payments": {
                "revenue_total_inr":      _rupees(money.get("total", 0)),
                "revenue_this_month_inr": _rupees(money.get("this_month", 0)),
                "avg_payment_inr":        _rupees(_avg(money.get("total", 0), captured_count, 0)),
                "captured":               captured_count,
                "failed":                 failed_count,
                "failure_rate_%":         _pct(failed_count, captured_count + failed_count),
                "distinct_payers":        len(payments.distinct("email", captured_match)),
                "by_plan":                plan_mix,
            },
            "content": {
                "resources": {
                    "total":       sum(resources_by_category.values()),
                    "by_category": resources_by_category,
                },
                "notifications": {
                    "sent":        total_notifs,
                    "read":        total_notifs - total_unread,
                    "unread":      total_unread,
                    "read_rate_%": _pct(total_notifs - total_unread, total_notifs),
                    "by_type": {
                        doc["_id"]: doc["count"]
                        for doc in notifications.aggregate([{"$group": {"_id": "$type", "count": {"$sum": 1}}}])
                    },
                },
            },
        }

    except Exception as e:
        logger.error("System: error fetching stats", extra={"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


def _build_segments(now: int, include_granted_access: bool) -> tuple:
    """Map every stat name to the set of emails behind it, plus a card per user.

    Backs both the inline lists in `needs_attention` and the /stats/segment
    drill-down, so a segment can never disagree with the number it came from.
    Classification reuses _lifecycle_stage — the counts and the lists are
    derived the same way by construction.
    """
    # Seeded so a segment that happens to be empty today returns an empty list
    # rather than a 404 — "nobody is stuck" is a valid answer, not a bad request.
    segments: dict = {name: set() for name in (
        "total_users", "counted_users", "comped_access", "new_this_month",
        "signed_up_only", "checkout_abandoned", "trial_active", "trial_expired",
        "paying", "winding_down", "churned",
        "hot", "warm", "cold", "converted", "no_trial", "unclassified",
        "lifetime_paying_customers", "trials_ending_in_7_days", "payment_halted",
        "vision_boards_failed", "vision_boards_stuck", "vision_board_users",
        "active_last_7_days", "active_last_30_days", "dormant",
        "chat_users", "eft_users", "guided_viz_users", "journal_users",
        "guided_viz_errors",
    )}
    cards: dict = {}

    def add(name: str, email: str):
        segments.setdefault(name, set()).add(email)

    month_start = _month_start_ts()
    excluded = set()
    counted = set()

    for doc in user_profile.find({}, _USER_CARD):
        email = doc.get("email")
        if not email:
            continue
        cards[email] = doc

        add("total_users", email)

        if doc.get("is_bypassed"):
            add("comped_access", email)
            if not include_granted_access:
                excluded.add(email)
                continue

        counted.add(email)
        add("counted_users", email)
        add(_lifecycle_stage(doc, now), email)
        add(doc.get("engagement_status") or "unclassified", email)

        if (doc.get("created_at") or 0) >= month_start:
            add("new_this_month", email)

        sub_status = doc.get("subscription_status")
        trial_end  = doc.get("trial_end_at") or 0

        if bool(doc.get("paid_until")) or sub_status in _EVER_PAID_STATUSES:
            add("lifetime_paying_customers", email)
        if trial_end and now < trial_end <= now + 7 * DAY:
            add("trials_ending_in_7_days", email)
        if sub_status == "halted":
            add("payment_halted", email)

        url = doc.get("vision_board_url") or ""
        if url == "failed":
            add("vision_boards_failed", email)
        elif url == "preparing":
            add("vision_boards_stuck", email)
        elif url:
            add("vision_board_users", email)

    segments["guided_viz_errors"] = {
        e for e in guided_viz_sessions.distinct("email", {"error": True})
        if e and e not in excluded
    }

    active_7, active_30 = _active_user_sets(now, excluded)
    segments["active_last_7_days"]  = active_7 & counted
    segments["active_last_30_days"] = active_30 & counted
    segments["dormant"]             = counted - active_30

    # Feature drill-downs come from the session collections, scoped the same way.
    for name, col in (
        ("chat_users", chat_sessions),
        ("eft_users", eft_sessions),
        ("guided_viz_users", guided_viz_sessions),
        ("journal_users", journal_log),
    ):
        segments[name] = {e for e in col.distinct("email") if e in counted}

    # Friendly aliases so the UI can pass the field name it rendered.
    for alias, source in (
        ("paying_customers", "paying"),
        ("on_free_trial", "trial_active"),
        ("winding_down_users", "winding_down"),
    ):
        if source in segments:
            segments[alias] = segments[source]

    return segments, cards


@stats_router.get("/stats/segment")
def get_stats_segment(
    segment: str = Query(..., description="Stat name to expand, e.g. trial_expired, payment_halted, chat_users"),
    include_granted_access: bool = Query(False, description="Same meaning as on /stats — keep it identical to the dashboard's current scope."),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    """The users behind any number on the stats dashboard."""
    try:
        now = int(time.time())
        segments, cards = _build_segments(now, include_granted_access)

        if segment not in segments:
            return JSONResponse(
                {"error": f"Unknown segment '{segment}'", "available": sorted(segments.keys())},
                status_code=404,
            )

        emails = sorted(segments[segment])
        # Most recent signups first — the useful order for outreach.
        emails.sort(key=lambda e: cards.get(e, {}).get("created_at") or 0, reverse=True)

        skip = (page - 1) * limit
        return {
            "segment": segment,
            "include_granted_access": include_granted_access,
            "total": len(emails),
            "page": page,
            "limit": limit,
            "users": [cards[e] for e in emails[skip: skip + limit] if e in cards],
        }

    except Exception as e:
        logger.error("System: error fetching stats segment", extra={"segment": segment, "error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)
