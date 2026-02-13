"""Composition and resolution endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from prompt_forge.api.models import ComposeRequest, ComposeResponse, ResolveRequest, VersionResponse
from prompt_forge.core.composer import CompositionEngine, get_composer
from prompt_forge.core.resolver import PromptResolver, get_resolver

router = APIRouter()


@router.post("/compose", response_model=ComposeResponse)
async def compose(
    data: ComposeRequest,
    composer: CompositionEngine = Depends(get_composer),
) -> ComposeResponse:
    """Compose an agent prompt from components."""
    try:
        result = composer.compose(
            persona_slug=data.persona,
            skill_slugs=data.skills,
            constraint_slugs=data.constraints,
            variables=data.variables,
            branch=data.branch,
            strategy=data.strategy,
        )
        return ComposeResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/resolve", response_model=VersionResponse)
async def resolve(
    data: ResolveRequest,
    resolver: PromptResolver = Depends(get_resolver),
) -> VersionResponse:
    """Resolve a single prompt component to a specific version."""
    version = resolver.resolve(
        slug=data.slug,
        branch=data.branch,
        version=data.version,
        strategy=data.strategy,
    )
    return VersionResponse(**version)
