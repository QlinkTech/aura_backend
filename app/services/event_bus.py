import asyncio
from collections import defaultdict

_loop: asyncio.AbstractEventLoop | None = None
_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def subscribe(email: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers[email].add(q)
    return q


def unsubscribe(email: str, q: asyncio.Queue) -> None:
    _subscribers[email].discard(q)
    if not _subscribers[email]:
        _subscribers.pop(email, None)


def publish(email: str, event: dict) -> None:
    """Thread-safe publish — safe to call from sync route handlers."""
    if not _loop:
        return
    for q in list(_subscribers.get(email, [])):
        _loop.call_soon_threadsafe(q.put_nowait, event)
