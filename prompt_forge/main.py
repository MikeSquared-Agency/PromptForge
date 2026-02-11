"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from prompt_forge.api.router import api_router
from prompt_forge.config import get_settings
from prompt_forge.db.client import get_supabase_client
from prompt_forge.utils.logging import setup_logging

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("promptforge.starting", port=settings.port)

    # Initialize Supabase client
    get_supabase_client()
    logger.info("promptforge.supabase_connected")

    yield

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


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "promptforge", "version": "0.1.0"}
