"""Version control endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from prompt_forge.api.models import (
    DiffResponse,
    FieldDiffResponse,
    RegressionWarning,
    RollbackRequest,
    VersionCreate,
    VersionPatch,
    VersionResponse,
    VersionRestoreRequest,
)
from prompt_forge.core.differ import StructuralDiffer
from prompt_forge.core.registry import PromptRegistry, get_registry
from prompt_forge.core.vcs import (
    VersionControl,
    get_vcs,
    merge_content,
    regression_check,
)
from prompt_forge.db.client import SupabaseClient, get_supabase_client

logger = structlog.get_logger()

router = APIRouter()


async def _auto_subscribe(
    prompt_id: str,
    agent_id: str | None,
    db: SupabaseClient,
) -> None:
    """Upsert subscription and update last_pulled_at."""
    if not agent_id:
        return
    existing = [
        r for r in db.select("prompt_subscriptions", filters={"prompt_id": prompt_id})
        if r["agent_id"] == agent_id
    ]
    now = datetime.now(timezone.utc).isoformat()
    if existing:
        db.update("prompt_subscriptions", existing[0]["id"], {"last_pulled_at": now})
    else:
        db.insert("prompt_subscriptions", {
            "prompt_id": prompt_id,
            "agent_id": agent_id,
            "subscribed_at": now,
            "last_pulled_at": now,
        })


async def _notify_subscribers(
    prompt_id: str,
    slug: str,
    old_version: int,
    new_version: int,
    change_note: str,
    priority: str,
    db: SupabaseClient,
) -> None:
    """Publish targeted events to all subscribers."""
    try:
        from prompt_forge.core.events import get_event_publisher
        publisher = get_event_publisher()
        if not publisher._connected:
            return

        subs = db.select("prompt_subscriptions", filters={"prompt_id": prompt_id})
        for sub in subs:
            agent_id = sub["agent_id"]
            subject = f"swarm.forge.agent.{agent_id}.prompt-updated"
            await publisher.publish(
                event_type="prompt.updated",
                subject=subject,
                data={
                    "slug": slug,
                    "prompt_id": prompt_id,
                    "old_version": old_version,
                    "new_version": new_version,
                    "change_note": change_note,
                    "priority": priority,
                },
            )
            logger.info("subscription.notified", agent_id=agent_id, slug=slug, new_version=new_version)
    except Exception as e:
        logger.warning("subscription.notify_failed", error=str(e))


async def _emit_regression_event(
    slug: str,
    event_type: str,
    regression: dict[str, Any],
    author: str,
) -> None:
    """Emit Hermes events for regression warnings/blocks."""
    try:
        from prompt_forge.core.events import get_event_publisher
        publisher = get_event_publisher()
        if not publisher._connected:
            return

        action = "version-warning" if event_type == "warning" else "version-blocked"
        subject = f"swarm.forge.{slug}.{action}"
        await publisher.publish(
            event_type=f"prompt.{action}",
            subject=subject,
            data={
                "slug": slug,
                "author": author,
                "keys_removed": regression["keys_removed"],
                "keys_added": regression["keys_added"],
                "content_reduction_pct": regression["content_reduction_pct"],
            },
        )
    except Exception as e:
        logger.warning("regression_event.publish_failed", error=str(e))


def _run_regression_guard(
    parent_content: dict[str, Any],
    new_content: dict[str, Any],
    acknowledge_reduction: bool,
    parent_version: int,
) -> dict[str, Any]:
    """Run regression check and return result. Raises HTTPException on block."""
    regression = regression_check(parent_content, new_content)

    if regression["block"] and not acknowledge_reduction:
        keys_unchanged = sorted(
            set(parent_content.keys()) & set(new_content.keys())
        )
        raise HTTPException(
            status_code=409,
            detail={
                "error": "content_regression_blocked",
                "message": (
                    f"New version removes {len(regression['keys_removed'])}/{len(parent_content)} "
                    f"keys and reduces content by {regression['content_reduction_pct']}%. "
                    "This looks accidental. To proceed, include "
                    '"acknowledge_reduction": true in your request.'
                ),
                "diff": {
                    "keys_removed": regression["keys_removed"],
                    "keys_added": regression["keys_added"],
                    "keys_unchanged": keys_unchanged,
                    "parent_version": parent_version,
                    "content_reduction_pct": regression["content_reduction_pct"],
                },
            },
        )

    return regression


@router.post("/{slug}/versions", response_model=VersionResponse, status_code=201)
async def create_version(
    slug: str,
    data: VersionCreate,
    registry: PromptRegistry = Depends(get_registry),
    vcs: VersionControl = Depends(get_vcs),
    db: SupabaseClient = Depends(get_supabase_client),
) -> VersionResponse:
    """Commit a new version of a prompt."""
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    prompt_id = str(prompt["id"])

    # Get current head
    history = vcs.history(prompt_id=prompt_id, branch=data.branch, limit=1)
    old_version = history[0]["version"] if history else 0
    parent_content = history[0]["content"] if history else None

    # Regression guard (only if there's a parent version to compare against)
    regression = None
    if parent_content is not None:
        regression = _run_regression_guard(
            parent_content, data.content, data.acknowledge_reduction, old_version
        )

    version = vcs.commit(
        prompt_id=prompt_id,
        content=data.content,
        message=data.message,
        author=data.author,
        branch=data.branch,
    )

    # Build response with warnings
    warnings = None
    if regression and regression["warn"]:
        warnings = [
            RegressionWarning(**w) for w in regression["warnings"]
        ]
        await _emit_regression_event(slug, "warning", regression, data.author)

    # Notify subscribers
    priority = data.priority or "normal"
    await _notify_subscribers(
        prompt_id=prompt_id,
        slug=slug,
        old_version=old_version,
        new_version=version["version"],
        change_note=data.message,
        priority=priority,
        db=db,
    )

    return VersionResponse(**version, warnings=warnings)


@router.patch("/{slug}/versions", response_model=VersionResponse, status_code=201)
async def patch_version(
    slug: str,
    data: VersionPatch,
    registry: PromptRegistry = Depends(get_registry),
    vcs: VersionControl = Depends(get_vcs),
    db: SupabaseClient = Depends(get_supabase_client),
) -> VersionResponse:
    """Merge fields into the latest version's content, creating a new version.

    Only send the fields you're changing/adding. Omitted fields are preserved.
    Set a field to null to remove it.
    """
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    prompt_id = str(prompt["id"])

    # Get current head — required for PATCH
    history = vcs.history(prompt_id=prompt_id, branch=data.branch, limit=1)
    if not history:
        raise HTTPException(
            status_code=404,
            detail=f"No versions found on branch '{data.branch}' — use POST to create the first version",
        )

    parent = history[0]
    merged_content = merge_content(parent["content"], data.content)

    # Regression guard
    regression = _run_regression_guard(
        parent["content"], merged_content, data.acknowledge_reduction, parent["version"]
    )

    version = vcs.commit(
        prompt_id=prompt_id,
        content=merged_content,
        message=data.message,
        author=data.author,
        branch=data.branch,
    )

    # Build response with warnings
    warnings = None
    if regression["warn"]:
        warnings = [
            RegressionWarning(**w) for w in regression["warnings"]
        ]
        await _emit_regression_event(slug, "warning", regression, data.author)

    # Notify subscribers
    priority = data.priority or "normal"
    await _notify_subscribers(
        prompt_id=prompt_id,
        slug=slug,
        old_version=parent["version"],
        new_version=version["version"],
        change_note=data.message,
        priority=priority,
        db=db,
    )

    return VersionResponse(**version, warnings=warnings)


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
    x_agent_id: str | None = Header(default=None, alias="X-Agent-ID"),
    registry: PromptRegistry = Depends(get_registry),
    vcs: VersionControl = Depends(get_vcs),
    db: SupabaseClient = Depends(get_supabase_client),
) -> VersionResponse:
    """Get a specific version."""
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    ver = vcs.get_version(prompt_id=str(prompt["id"]), version=version, branch=branch)
    if not ver:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")

    # Auto-subscribe
    await _auto_subscribe(str(prompt["id"]), x_agent_id, db)

    return VersionResponse(**ver)


@router.get("/{slug}/versions/{version_a}/diff/{version_b}", response_model=FieldDiffResponse)
async def field_diff_versions(
    slug: str,
    version_a: int,
    version_b: int,
    branch: str = "main",
    registry: PromptRegistry = Depends(get_registry),
    vcs: VersionControl = Depends(get_vcs),
) -> FieldDiffResponse:
    """Get a field-level diff between any two versions.

    Compares top-level content keys, showing which were added, removed, or modified.
    """
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    prompt_id = str(prompt["id"])
    v_from = vcs.get_version(prompt_id=prompt_id, version=version_a, branch=branch)
    v_to = vcs.get_version(prompt_id=prompt_id, version=version_b, branch=branch)

    if not v_from or not v_to:
        raise HTTPException(status_code=404, detail="One or both versions not found")

    differ = StructuralDiffer()
    result = differ.field_diff(
        v_from["content"], v_to["content"],
        from_version=version_a, to_version=version_b,
    )

    return FieldDiffResponse(**result)


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


@router.post("/{slug}/versions/restore", response_model=VersionResponse, status_code=201)
async def restore_version(
    slug: str,
    data: VersionRestoreRequest,
    registry: PromptRegistry = Depends(get_registry),
    vcs: VersionControl = Depends(get_vcs),
    db: SupabaseClient = Depends(get_supabase_client),
) -> VersionResponse:
    """Restore a historical version, optionally merging with a patch.

    Creates a new version by copying content from from_version,
    then merging any provided patch fields on top.
    """
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    prompt_id = str(prompt["id"])

    # Get the version to restore from
    source = vcs.get_version(prompt_id=prompt_id, version=data.from_version, branch=data.branch)
    if not source:
        raise HTTPException(
            status_code=404,
            detail=f"Version {data.from_version} not found on branch '{data.branch}'",
        )

    restored_content = dict(source["content"])
    if data.patch:
        restored_content = merge_content(restored_content, data.patch)

    message = data.message or f"Restore from version {data.from_version}"

    # Get current head for regression guard
    history = vcs.history(prompt_id=prompt_id, branch=data.branch, limit=1)
    parent = history[0] if history else None

    # Regression guard against current head
    regression = None
    if parent:
        regression = _run_regression_guard(
            parent["content"], restored_content, data.acknowledge_reduction, parent["version"]
        )

    version = vcs.commit(
        prompt_id=prompt_id,
        content=restored_content,
        message=message,
        author=data.author,
        branch=data.branch,
    )

    # Build response with warnings
    warnings = None
    if regression and regression["warn"]:
        warnings = [
            RegressionWarning(**w) for w in regression["warnings"]
        ]
        await _emit_regression_event(slug, "warning", regression, data.author)

    # Notify subscribers
    old_version = parent["version"] if parent else 0
    priority = data.priority or "normal"
    await _notify_subscribers(
        prompt_id=prompt_id,
        slug=slug,
        old_version=old_version,
        new_version=version["version"],
        change_note=message,
        priority=priority,
        db=db,
    )

    return VersionResponse(**version, warnings=warnings)


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
