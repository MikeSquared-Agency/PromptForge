"""Persona convenience endpoints — thin wrappers over the prompt resolver."""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from prompt_forge.api.models import VersionResponse
from prompt_forge.core.resolver import PromptResolver, get_resolver

logger = structlog.get_logger()

router = APIRouter()

ALEXANDRIA_URL = os.getenv("ALEXANDRIA_URL", "")


@router.get("/{persona}", response_model=VersionResponse)
async def get_persona(
    persona: str,
    branch: str = Query("main"),
    strategy: str = Query("latest"),
    resolver: PromptResolver = Depends(get_resolver),
) -> VersionResponse:
    """Get the latest version of a persona prompt."""
    try:
        version = resolver.resolve(slug=persona, branch=branch, strategy=strategy)
        return VersionResponse(**version)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{persona}/{version}", response_model=VersionResponse)
async def get_persona_version(
    persona: str,
    version: int,
    branch: str = Query("main"),
    resolver: PromptResolver = Depends(get_resolver),
) -> VersionResponse:
    """Get a specific version of a persona prompt."""
    try:
        result = resolver.resolve(slug=persona, branch=branch, version=version, strategy="pinned")
        return VersionResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{persona}/effective")
async def get_persona_effective(
    persona: str,
    branch: str = Query("main"),
    strategy: str = Query("latest"),
    resolver: PromptResolver = Depends(get_resolver),
) -> dict[str, Any]:
    """Get latest persona version merged with Alexandria context (if configured)."""
    try:
        version = resolver.resolve(slug=persona, branch=branch, strategy=strategy)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    result: dict[str, Any] = {
        "version": VersionResponse(**version).model_dump(mode="json"),
        "alexandria_context": None,
    }

    if ALEXANDRIA_URL:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{ALEXANDRIA_URL}/api/v1/context/{persona}",
                )
                if resp.status_code == 200:
                    result["alexandria_context"] = resp.json()
                else:
                    logger.warning(
                        "personas.alexandria_unavailable",
                        persona=persona,
                        status=resp.status_code,
                    )
        except httpx.HTTPError as exc:
            logger.warning("personas.alexandria_error", persona=persona, error=str(exc))

    return result
