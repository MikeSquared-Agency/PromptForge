"""Version control endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from prompt_forge.api.models import (
    DiffResponse,
    RollbackRequest,
    VersionCreate,
    VersionResponse,
)
from prompt_forge.core.differ import StructuralDiffer
from prompt_forge.core.registry import PromptRegistry, get_registry
from prompt_forge.core.vcs import VersionControl, get_vcs

router = APIRouter()


@router.post("/{slug}/versions", response_model=VersionResponse, status_code=201)
async def create_version(
    slug: str,
    data: VersionCreate,
    registry: PromptRegistry = Depends(get_registry),
    vcs: VersionControl = Depends(get_vcs),
) -> VersionResponse:
    """Commit a new version of a prompt."""
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    version = vcs.commit(
        prompt_id=str(prompt["id"]),
        content=data.content,
        message=data.message,
        author=data.author,
        branch=data.branch,
    )
    return VersionResponse(**version)


@router.get("/{slug}/versions", response_model=list[VersionResponse])
async def list_versions(
    slug: str,
    branch: str = "main",
    limit: int = Query(default=50, le=200),
    registry: PromptRegistry = Depends(get_registry),
    vcs: VersionControl = Depends(get_vcs),
) -> list[VersionResponse]:
    """Get version history for a prompt."""
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    versions = vcs.history(prompt_id=str(prompt["id"]), branch=branch, limit=limit)
    return [VersionResponse(**v) for v in versions]


@router.get("/{slug}/versions/{version}", response_model=VersionResponse)
async def get_version(
    slug: str,
    version: int,
    branch: str = "main",
    registry: PromptRegistry = Depends(get_registry),
    vcs: VersionControl = Depends(get_vcs),
) -> VersionResponse:
    """Get a specific version."""
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    ver = vcs.get_version(prompt_id=str(prompt["id"]), version=version, branch=branch)
    if not ver:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    return VersionResponse(**ver)


@router.get("/{slug}/diff", response_model=DiffResponse)
async def diff_versions(
    slug: str,
    from_version: int = Query(..., alias="from"),
    to_version: int = Query(..., alias="to"),
    branch: str = "main",
    registry: PromptRegistry = Depends(get_registry),
    vcs: VersionControl = Depends(get_vcs),
) -> DiffResponse:
    """Get structural diff between two versions."""
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    prompt_id = str(prompt["id"])
    v_from = vcs.get_version(prompt_id=prompt_id, version=from_version, branch=branch)
    v_to = vcs.get_version(prompt_id=prompt_id, version=to_version, branch=branch)

    if not v_from or not v_to:
        raise HTTPException(status_code=404, detail="One or both versions not found")

    differ = StructuralDiffer()
    diff = differ.diff(v_from["content"], v_to["content"])

    return DiffResponse(
        prompt_id=prompt["id"],
        from_version=from_version,
        to_version=to_version,
        changes=diff["changes"],
        summary=diff["summary"],
    )


@router.post("/{slug}/rollback", response_model=VersionResponse)
async def rollback_version(
    slug: str,
    data: RollbackRequest,
    registry: PromptRegistry = Depends(get_registry),
    vcs: VersionControl = Depends(get_vcs),
) -> VersionResponse:
    """Rollback to a previous version."""
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    version = vcs.rollback(
        prompt_id=str(prompt["id"]),
        version=data.version,
        author=data.author,
    )
    if not version:
        raise HTTPException(status_code=404, detail=f"Version {data.version} not found")
    return VersionResponse(**version)
