"""PromptArchitect conversation endpoints."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from prompt_forge.architect.agent import PromptArchitect
from prompt_forge.core.composer import CompositionEngine, get_composer
from prompt_forge.core.registry import PromptRegistry, get_registry
from prompt_forge.core.vcs import VersionControl, get_vcs

router = APIRouter(prefix="/architect", tags=["architect"])


class DesignRequest(BaseModel):
    """Design a new prompt."""
    requirements: str = Field(..., min_length=1)
    type: str = Field(default="persona", pattern=r"^(persona|skill|constraint|template|meta)$")


class RefineRequest(BaseModel):
    """Refine an existing prompt."""
    slug: str
    feedback: str = Field(..., min_length=1)


class EvaluateRequest(BaseModel):
    """Evaluate a prompt."""
    slug: str


def _get_architect(
    registry: PromptRegistry = Depends(get_registry),
    vcs: VersionControl = Depends(get_vcs),
    composer: CompositionEngine = Depends(get_composer),
) -> PromptArchitect:
    return PromptArchitect(registry, vcs, composer)


@router.post("/design")
async def design_prompt(
    data: DesignRequest,
    architect: PromptArchitect = Depends(_get_architect),
) -> dict[str, Any]:
    """Design a new prompt from natural language requirements."""
    try:
        result = await architect.design(data.requirements, data.type)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/refine")
async def refine_prompt(
    data: RefineRequest,
    architect: PromptArchitect = Depends(_get_architect),
) -> dict[str, Any]:
    """Refine an existing prompt based on feedback."""
    try:
        result = await architect.refine(data.slug, data.feedback)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/evaluate")
async def evaluate_prompt(
    data: EvaluateRequest,
    architect: PromptArchitect = Depends(_get_architect),
) -> dict[str, Any]:
    """Evaluate prompt quality."""
    try:
        report = await architect.evaluate(data.slug)
        return asdict(report)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
