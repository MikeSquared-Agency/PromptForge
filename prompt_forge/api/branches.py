"""Branch management endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from prompt_forge.core.registry import PromptRegistry, get_registry
from prompt_forge.core.vcs import VersionControl, get_vcs

router = APIRouter()


class BranchCreate(BaseModel):
    """Create a branch."""

    name: str = Field(..., min_length=1, max_length=100)
    from_branch: str = "main"


class BranchMerge(BaseModel):
    """Merge a branch."""

    strategy: str = Field(default="theirs", pattern=r"^(ours|theirs|section_merge)$")
    author: str = "system"


class BranchResponse(BaseModel):
    """Branch info."""

    id: str
    prompt_id: str
    name: str
    head_version_id: str | None
    base_version_id: str | None
    status: str
    created_at: str
    updated_at: str


@router.post("/{slug}/branches", status_code=201)
async def create_branch(
    slug: str,
    data: BranchCreate,
    registry: PromptRegistry = Depends(get_registry),
    vcs: VersionControl = Depends(get_vcs),
) -> dict[str, Any]:
    """Create a new branch for a prompt."""
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    try:
        branch = vcs.create_branch(
            prompt_id=str(prompt["id"]),
            branch_name=data.name,
            from_branch=data.from_branch,
        )
        return branch
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{slug}/branches")
async def list_branches(
    slug: str,
    registry: PromptRegistry = Depends(get_registry),
    vcs: VersionControl = Depends(get_vcs),
) -> list[dict[str, Any]]:
    """List all branches for a prompt."""
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    return vcs.list_branches(str(prompt["id"]))


@router.post("/{slug}/branches/{branch_name}/merge")
async def merge_branch(
    slug: str,
    branch_name: str,
    data: BranchMerge,
    registry: PromptRegistry = Depends(get_registry),
    vcs: VersionControl = Depends(get_vcs),
) -> dict[str, Any]:
    """Merge a branch into main (or target)."""
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    try:
        version = vcs.merge_branch(
            prompt_id=str(prompt["id"]),
            source_branch=branch_name,
            target_branch="main",
            strategy=data.strategy,
            author=data.author,
        )
        return version
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
