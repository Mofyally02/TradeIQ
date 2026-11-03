import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api import (
    accounts,
    admin,
    agent,
    auth,
    dashboard,
    development,
    devices,
    ea,
    integrations,
    mt5_connector,
    performance,
    plans,
    platform,
    profile,
    risk,
    trades,
)
from app.core.config import get_settings
from app.db import engine

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = None
    if settings.metaapi_token:
        from app.services.metaapi import sync_all_loop

        task = asyncio.create_task(sync_all_loop())
    yield
    if task is not None:
        task.cancel()


app = FastAPI(title="TradeIQ API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.web_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def enforce_browser_origin(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and origin not in settings.web_origins:
            return JSONResponse(status_code=403, content={"detail": "Origin is not allowed"})
    return await call_next(request)


app.include_router(auth.router, prefix="/api/v1")
app.include_router(plans.router, prefix="/api/v1")
app.include_router(profile.router, prefix="/api/v1")
app.include_router(accounts.router, prefix="/api/v1")
app.include_router(trades.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(performance.router, prefix="/api/v1")
app.include_router(agent.router, prefix="/api/v1")
app.include_router(risk.router, prefix="/api/v1")
app.include_router(integrations.router, prefix="/api/v1")
app.include_router(mt5_connector.router, prefix="/api/v1")
app.include_router(ea.router, prefix="/api/v1")
app.include_router(development.router, prefix="/api/v1")
app.include_router(devices.public_router, prefix="/api/v1")
app.include_router(devices.router, prefix="/api/v1")
app.include_router(platform.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(admin.mfa_router, prefix="/api/v1")


@app.get("/healthz", tags=["Operations"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", tags=["Operations"])
def readiness() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Database readiness check failed")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ready"}
