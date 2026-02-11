"""Prompt CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from prompt_forge.api.models import PromptCreate, PromptResponse, PromptUpdate
from prompt_forge.core.registry import PromptRegistry, get_registry

router = APIRouter()


@router.post("", response_model=PromptResponse, status_code=201)
async def create_prompt(
    data: PromptCreate,
    registry: PromptRegistry = Depends(get_registry),
) -> PromptResponse:
    """Create a new prompt with an optional initial version."""
    try:
        prompt = registry.create_prompt(
            slug=data.slug,
            name=data.name,
            type=data.type,
            description=data.description,
            tags=data.tags,
            metadata=data.metadata,
            content=data.content,
            initial_message=data.initial_message,
        )
        return PromptResponse(**prompt)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("", response_model=list[PromptResponse])
async def list_prompts(
    type: str | None = None,
    tag: str | None = None,
    search: str | None = None,
    archived: bool = False,
    registry: PromptRegistry = Depends(get_registry),
) -> list[PromptResponse]:
    """List prompts with optional filters."""
    prompts = registry.list_prompts(type=type, tag=tag, search=search, archived=archived)
    return [PromptResponse(**p) for p in prompts]


@router.get("/{slug}", response_model=PromptResponse)
async def get_prompt(
    slug: str,
    registry: PromptRegistry = Depends(get_registry),
) -> PromptResponse:
    """Get a prompt by slug."""
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")
    return PromptResponse(**prompt)


@router.put("/{slug}", response_model=PromptResponse)
async def update_prompt(
    slug: str,
    data: PromptUpdate,
    registry: PromptRegistry = Depends(get_registry),
) -> PromptResponse:
    """Update a prompt's metadata."""
    prompt = registry.update_prompt(slug, **data.model_dump(exclude_none=True))
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")
    return PromptResponse(**prompt)


@router.delete("/{slug}", status_code=204)
async def archive_prompt(
    slug: str,
    registry: PromptRegistry = Depends(get_registry),
) -> None:
    """Archive (soft delete) a prompt."""
    success = registry.archive_prompt(slug)
    if not success:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")
