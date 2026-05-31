import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from app.routes.auth import auth_router
from app.routes.user import user_router
from app.routes.systems import system_router
from app.routes.payment import payment_router
from app.services.event_bus import set_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    set_loop(asyncio.get_event_loop())
    yield


app = FastAPI(
    title="Menifest my dreams - qlink",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

 
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://sanaya-dashboard.vercel.app",
        "https://app.regulatewithaura.com",
        "https://app.manifestwithaura.com",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/ping", tags=["Health"])
def ping():
    return {"status": "ok", "message": "MMD - Qlink backend is running perfectly fine."}

app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(user_router, prefix="/api/user", tags=["User"])
app.include_router(system_router, prefix="/api/system", tags=["Systems"])
app.include_router(payment_router, prefix="/api/payment", tags=["Payment"])

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
