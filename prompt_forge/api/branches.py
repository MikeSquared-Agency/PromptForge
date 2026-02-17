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


class BranchReject(BaseModel):
    """Reject a branch."""

    reason: str | None = None


class BranchDiffResponse(BaseModel):
    """Branch diff response."""

    branch_name: str
    target_section: str = "all"
    current_content: dict[str, Any]
    proposed_content: dict[str, Any]
    diff_summary: str


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


@router.get("/{slug}/branches/{branch_name}/diff")
async def branch_diff(
    slug: str,
    branch_name: str,
    registry: PromptRegistry = Depends(get_registry),
    vcs: VersionControl = Depends(get_vcs),
) -> dict[str, Any]:
    """Compare branch head version content vs main branch latest version content."""
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    prompt_id = str(prompt["id"])

    # Check if branch exists
    branches = vcs.list_branches(prompt_id)
    branch = next((b for b in branches if b["name"] == branch_name), None)
    if not branch:
        raise HTTPException(status_code=404, detail=f"Branch '{branch_name}' not found")

    try:
        # Get latest version from the branch
        branch_history = vcs.history(prompt_id, branch=branch_name, limit=1)
        if not branch_history:
            raise HTTPException(
                status_code=404, detail=f"No versions found on branch '{branch_name}'"
            )

        branch_version = branch_history[0]
        proposed_content = branch_version["content"]

        # Get latest version from main branch
        main_history = vcs.history(prompt_id, branch="main", limit=1)
        if not main_history:
            raise HTTPException(status_code=404, detail="No versions found on main branch")

        main_version = main_history[0]
        current_content = main_version["content"]

        # Generate diff summary
        diff_summary = _generate_diff_summary(current_content, proposed_content)

        return {
            "branch_name": branch_name,
            "target_section": "all",
            "current_content": current_content,
            "proposed_content": proposed_content,
            "diff_summary": diff_summary,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating diff: {str(e)}")


@router.post("/{slug}/branches/{branch_name}/reject")
async def reject_branch(
    slug: str,
    branch_name: str,
    data: BranchReject,
    registry: PromptRegistry = Depends(get_registry),
    vcs: VersionControl = Depends(get_vcs),
) -> dict[str, Any]:
    """Reject a branch by updating its status."""
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    prompt_id = str(prompt["id"])

    # Check if branch exists
    branches = vcs.list_branches(prompt_id)
    branch = next((b for b in branches if b["name"] == branch_name), None)
    if not branch:
        raise HTTPException(status_code=404, detail=f"Branch '{branch_name}' not found")

    try:
        # Update branch status to rejected
        updated_branch = vcs.db.update("prompt_branches", branch["id"], {"status": "rejected"})
        return updated_branch

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error rejecting branch: {str(e)}")


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


def _generate_diff_summary(current: dict[str, Any], proposed: dict[str, Any]) -> str:
    """Generate a human-readable summary of differences."""
    changes = []

    # Compare sections
    current_sections = {s.get("id"): s for s in current.get("sections", [])}
    proposed_sections = {s.get("id"): s for s in proposed.get("sections", [])}

    # New sections
    new_sections = set(proposed_sections.keys()) - set(current_sections.keys())
    if new_sections:
        changes.append(f"Added {len(new_sections)} new section(s): {', '.join(new_sections)}")

    # Removed sections
    removed_sections = set(current_sections.keys()) - set(proposed_sections.keys())
    if removed_sections:
        changes.append(f"Removed {len(removed_sections)} section(s): {', '.join(removed_sections)}")

    # Modified sections
    modified_sections = []
    for section_id in set(current_sections.keys()) & set(proposed_sections.keys()):
        if current_sections[section_id].get("content") != proposed_sections[section_id].get(
            "content"
        ):
            modified_sections.append(section_id)

    if modified_sections:
        changes.append(
            f"Modified {len(modified_sections)} section(s): {', '.join(modified_sections)}"
        )

    # Compare variables
    current_vars = current.get("variables", {})
    proposed_vars = proposed.get("variables", {})

    new_vars = set(proposed_vars.keys()) - set(current_vars.keys())
    removed_vars = set(current_vars.keys()) - set(proposed_vars.keys())
    modified_vars = [
        k
        for k in set(current_vars.keys()) & set(proposed_vars.keys())
        if current_vars[k] != proposed_vars[k]
    ]

    if new_vars:
        changes.append(f"Added {len(new_vars)} variable(s)")
    if removed_vars:
        changes.append(f"Removed {len(removed_vars)} variable(s)")
    if modified_vars:
        changes.append(f"Modified {len(modified_vars)} variable(s)")

    # Compare metadata
    current_meta = current.get("metadata", {})
    proposed_meta = proposed.get("metadata", {})

    if current_meta != proposed_meta:
        changes.append("Modified metadata")

    if not changes:
        return "No changes detected"

    return "; ".join(changes)
