"""Persona prompt versioning API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from prompt_forge.api.models import PersonaPromptCreate, PersonaPromptResponse
from prompt_forge.db.persona_store import PersonaPromptStore, get_persona_store

router = APIRouter()


@router.get("/{persona}", response_model=PersonaPromptResponse)
async def get_persona_prompt_latest(
    persona: str,
    store: PersonaPromptStore = Depends(get_persona_store),
) -> PersonaPromptResponse:
    """Get the latest version of a persona prompt."""
    prompt = store.get_latest_persona_prompt(persona)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Persona '{persona}' not found")

    return PersonaPromptResponse(**prompt.model_dump())


@router.post("/seed", status_code=201)
async def seed_initial_personas(
    store: PersonaPromptStore = Depends(get_persona_store),
) -> dict[str, str]:
    """Seed initial personas with basic templates."""
    try:
        store.seed_initial_personas()
        return {"message": "Initial personas seeded successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to seed personas: {str(e)}")


@router.get("/{persona}/versions", response_model=list[PersonaPromptResponse])
async def list_persona_prompt_versions(
    persona: str,
    store: PersonaPromptStore = Depends(get_persona_store),
) -> list[PersonaPromptResponse]:
    """List all versions of a persona prompt."""
    prompts = store.list_persona_versions(persona)
    if not prompts:
        raise HTTPException(status_code=404, detail=f"Persona '{persona}' not found")

    return [PersonaPromptResponse(**prompt.model_dump()) for prompt in prompts]


@router.post("/{persona}", response_model=PersonaPromptResponse, status_code=201)
async def create_persona_prompt_version(
    persona: str,
    data: PersonaPromptCreate,
    store: PersonaPromptStore = Depends(get_persona_store),
) -> PersonaPromptResponse:
    """Create a new version of a persona prompt (auto-increments version, sets previous is_latest=false)."""
    try:
        prompt = store.create_persona_prompt_version(persona, data.template)
        return PersonaPromptResponse(**prompt.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create persona prompt: {str(e)}")


@router.get("/{persona}/{version}", response_model=PersonaPromptResponse)
async def get_persona_prompt_version(
    persona: str,
    version: int,
    store: PersonaPromptStore = Depends(get_persona_store),
) -> PersonaPromptResponse:
    """Get a specific version of a persona prompt."""
    prompt = store.get_persona_prompt_version(persona, version)
    if not prompt:
        raise HTTPException(
            status_code=404, detail=f"Persona '{persona}' version {version} not found"
        )

    return PersonaPromptResponse(**prompt.model_dump())
