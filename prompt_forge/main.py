"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from prompt_forge.api.router import api_router
from prompt_forge.config import get_settings
from prompt_forge.db.client import get_supabase_client
from prompt_forge.utils.logging import setup_logging

logger = structlog.get_logger()

_cleanup_task = None
_analyser_task = None
_autonomy_task = None


async def subscription_ttl_cleanup():
    """Background task: delete stale subscriptions every hour."""
    while True:
        try:
            await asyncio.sleep(3600)  # 1 hour
            db = get_supabase_client()
            cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            subs = db.select("prompt_subscriptions")
            stale = [s for s in subs if s.get("last_pulled_at", "") < cutoff]
            for s in stale:
                db.delete("prompt_subscriptions", s["id"])
            if stale:
                logger.info("subscriptions.ttl_cleanup", removed=len(stale))
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("subscriptions.ttl_cleanup_error", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    global _cleanup_task
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("promptforge.starting", port=settings.port)

    # Initialize Supabase client
    get_supabase_client()
    logger.info("promptforge.supabase_connected")

    # Initialize NATS event publisher (optional)
    try:
        from prompt_forge.core.events import get_event_publisher

        publisher = get_event_publisher()
        await publisher.connect()
    except Exception as e:
        logger.info("promptforge.nats_skipped", reason=str(e))

    # Initialize NATS effectiveness subscribers (optional)
    try:
        from prompt_forge.core.subscribers import get_effectiveness_subscriber

        subscriber = get_effectiveness_subscriber()
        if await subscriber.connect():
            await subscriber.start()
    except Exception as e:
        logger.info("promptforge.subscribers_skipped", reason=str(e))

    # Start TTL cleanup background task
    _cleanup_task = asyncio.create_task(subscription_ttl_cleanup())

    # Start analyser and autonomy background tasks
    global _analyser_task, _autonomy_task
    try:
        from prompt_forge.core.analyser import run_analyser_loop

        _analyser_task = asyncio.create_task(run_analyser_loop())
    except Exception as e:
        logger.info("promptforge.analyser_skipped", reason=str(e))

    try:
        from prompt_forge.core.autonomy import run_autonomy_loop

        _autonomy_task = asyncio.create_task(run_autonomy_loop())
    except Exception as e:
        logger.info("promptforge.autonomy_skipped", reason=str(e))

    yield

    # Cancel background tasks
    for task in (_cleanup_task, _analyser_task, _autonomy_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    # Disconnect NATS subscribers
    try:
        from prompt_forge.core.subscribers import get_effectiveness_subscriber

        subscriber = get_effectiveness_subscriber()
        await subscriber.stop()
    except Exception:
        pass

    # Disconnect NATS
    try:
        from prompt_forge.core.events import get_event_publisher

        publisher = get_event_publisher()
        await publisher.disconnect()
    except Exception:
        pass

    logger.info("promptforge.shutdown")


app = FastAPI(
    title="PromptForge",
    description="Centralised prompt lifecycle management for OpenClaw agent swarms",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Service info endpoint."""
    return {"service": "promptforge", "version": "0.1.0"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "promptforge", "version": "0.1.0"}
