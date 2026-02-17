"""Refinement proposals endpoints."""

from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from prompt_forge.core.registry import PromptRegistry, get_registry
from prompt_forge.core.vcs import VersionControl, get_vcs
from prompt_forge.db.client import SupabaseClient, get_supabase_client

router = APIRouter()


class ProposalResponse(BaseModel):
    """Refinement proposal response."""

    branch_name: str
    created_at: str
    target_section: str | None = None
    source_patterns: list[str] = []


@router.get("/{slug}/proposals", response_model=list[ProposalResponse])
async def list_refinement_proposals(
    slug: str,
    registry: PromptRegistry = Depends(get_registry),
    vcs: VersionControl = Depends(get_vcs),
    db: SupabaseClient = Depends(get_supabase_client),
) -> list[ProposalResponse]:
    """List pending refinement branches for a prompt.

    Returns branches with name prefix 'refinement/' and status 'active'.
    """
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    prompt_id = str(prompt["id"])

    # Get all active branches for this prompt
    all_branches = vcs.list_branches(prompt_id)

    # Filter for refinement branches with active status
    refinement_branches = [
        branch
        for branch in all_branches
        if branch["name"].startswith("refinement/") and branch["status"] == "active"
    ]

    proposals = []
    for branch in refinement_branches:
        # Extract target section from branch name (refinement/{section}/{timestamp})
        name_parts = branch["name"].split("/")
        target_section = name_parts[1] if len(name_parts) >= 2 else None

        # Try to get source patterns from metadata (optional)
        source_patterns = []
        try:
            metadata_rows = db.select("refinement_proposals", filters={"branch_id": branch["id"]})
            if metadata_rows:
                source_patterns = metadata_rows[0].get("source_patterns", [])
        except Exception:
            # Table might not exist or have different structure
            pass

        proposals.append(
            ProposalResponse(
                branch_name=branch["name"],
                created_at=branch["created_at"],
                target_section=target_section,
                source_patterns=source_patterns,
            )
        )

    # Sort by creation time (newest first)
    proposals.sort(key=lambda p: p.created_at, reverse=True)

    return proposals
