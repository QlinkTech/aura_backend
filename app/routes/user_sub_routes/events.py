import asyncio
import json

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.services import event_bus
from app.services.auth_service import get_current_user
from app.utils.logger_config import logger

events_router = APIRouter()

KEEPALIVE_SECONDS = 25


@events_router.get("/events")
async def stream_events(current_user: dict = Depends(get_current_user)):
    email = current_user["email"]
    logger.info("SSE client connected", extra={"email": email})

    async def generator():
        q = event_bus.subscribe(email)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=KEEPALIVE_SECONDS)
                    yield {"data": json.dumps(event)}
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(email, q)
            logger.info("SSE client disconnected", extra={"email": email})

    return EventSourceResponse(generator())
