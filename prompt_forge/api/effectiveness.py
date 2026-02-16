"""Prompt effectiveness tracking endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from prompt_forge.api.models import (
    EffectivenessCreate,
    EffectivenessResponse,
    EffectivenessSummary,
    EffectivenessUpdate,
    ModelEffectivenessResponse,
)
from prompt_forge.db.client import SupabaseClient, get_supabase_client

logger = structlog.get_logger()
router = APIRouter()


@router.post("/effectiveness", status_code=201, response_model=EffectivenessResponse)
async def create_effectiveness(
    data: EffectivenessCreate,
    db: SupabaseClient = Depends(get_supabase_client),
) -> EffectivenessResponse:
    """Create an effectiveness tracking record at session spawn."""
    row = db.insert(
        "prompt_effectiveness",
        {
            "session_uuid": data.session_uuid,
            "prompt_id": str(data.prompt_id) if data.prompt_id else None,
            "version_id": str(data.version_id) if data.version_id else None,
            "agent_id": data.agent_id,
            "model_id": data.model_id,
            "model_tier": data.model_tier,
            "briefing_hash": data.briefing_hash,
            "mission_id": data.mission_id,
            "task_id": data.task_id,
        },
    )
    return _row_to_response(row)


@router.patch("/effectiveness/{session_uuid}", response_model=EffectivenessResponse)
async def update_effectiveness(
    session_uuid: str,
    data: EffectivenessUpdate,
    db: SupabaseClient = Depends(get_supabase_client),
) -> EffectivenessResponse:
    """Update effectiveness record with tokens/corrections/outcome."""
    rows = db.select("prompt_effectiveness", filters={"session_uuid": session_uuid})
    if not rows:
        raise HTTPException(status_code=404, detail=f"No record for session {session_uuid}")

    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if updates.get("completed_at"):
        updates["completed_at"] = updates["completed_at"].isoformat()
    if not updates:
        return _row_to_response(rows[0])

    row = db.update("prompt_effectiveness", rows[0]["id"], updates)
    return _row_to_response(row)


@router.get("/effectiveness/summary", response_model=list[EffectivenessSummary])
async def effectiveness_summary(
    group_by: str = Query(
        default="version_id", pattern=r"^(version_id|model_id|agent_id|model_tier)$"
    ),
    prompt_id: UUID | None = None,
    model_id: str | None = None,
    agent_id: str | None = None,
    days: int = Query(default=30, ge=1, le=365),
    db: SupabaseClient = Depends(get_supabase_client),
) -> list[EffectivenessSummary]:
    """Aggregated effectiveness stats, filterable by prompt/model/agent/time."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    rows = db.select("prompt_effectiveness")
    filtered = [r for r in rows if r.get("created_at", "") >= cutoff]
    if prompt_id:
        filtered = [r for r in filtered if r.get("prompt_id") == str(prompt_id)]
    if model_id:
        filtered = [r for r in filtered if r.get("model_id") == model_id]
    if agent_id:
        filtered = [r for r in filtered if r.get("agent_id") == agent_id]

    groups: dict[str, list[dict]] = {}
    for r in filtered:
        key = r.get(group_by) or "unknown"
        groups.setdefault(str(key), []).append(r)

    summaries = []
    for gval, records in groups.items():
        count = len(records)
        tokens = [r.get("total_tokens") for r in records if r.get("total_tokens")]
        costs = [r.get("cost_usd") for r in records if r.get("cost_usd")]
        scores = [r.get("outcome_score") for r in records if r.get("outcome_score") is not None]
        effs = [r.get("effectiveness") for r in records if r.get("effectiveness") is not None]
        corrections = sum(r.get("correction_count", 0) for r in records)

        summaries.append(
            EffectivenessSummary(
                group_key=group_by,
                group_value=gval,
                session_count=count,
                avg_tokens=sum(tokens) / len(tokens) if tokens else None,
                avg_cost_usd=sum(costs) / len(costs) if costs else None,
                avg_outcome_score=sum(scores) / len(scores) if scores else None,
                avg_effectiveness=sum(effs) / len(effs) if effs else None,
                total_corrections=corrections,
                correction_rate=corrections / count if count > 0 else None,
            )
        )
    return summaries


@router.get("/effectiveness/model-tiers", response_model=ModelEffectivenessResponse)
async def model_tier_effectiveness(
    days: int = Query(default=30, ge=1, le=365),
    db: SupabaseClient = Depends(get_supabase_client),
) -> ModelEffectivenessResponse:
    """Correction rate and avg effectiveness per model tier (Dispatch consumes this)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = db.select("prompt_effectiveness")
    filtered = [r for r in rows if r.get("created_at", "") >= cutoff]

    tiers: dict[str, list[dict]] = {}
    for r in filtered:
        tier = r.get("model_tier") or "unknown"
        tiers.setdefault(tier, []).append(r)

    result = {}
    for tier_name in ("economy", "standard", "premium"):
        records = tiers.get(tier_name, [])
        if not records:
            continue
        count = len(records)
        corrections = sum(r.get("correction_count", 0) for r in records)
        effs = [r.get("effectiveness") for r in records if r.get("effectiveness") is not None]
        scores = [r.get("outcome_score") for r in records if r.get("outcome_score") is not None]
        result[tier_name] = EffectivenessSummary(
            group_key="model_tier",
            group_value=tier_name,
            session_count=count,
            avg_tokens=None,
            avg_cost_usd=None,
            avg_outcome_score=sum(scores) / len(scores) if scores else None,
            avg_effectiveness=sum(effs) / len(effs) if effs else None,
            total_corrections=corrections,
            correction_rate=corrections / count if count > 0 else None,
        )

    return ModelEffectivenessResponse(**result)


@router.get("/effectiveness/prompt/{slug}/versions", response_model=list[EffectivenessSummary])
async def prompt_version_effectiveness(
    slug: str,
    days: int = Query(default=30, ge=1, le=365),
    db: SupabaseClient = Depends(get_supabase_client),
) -> list[EffectivenessSummary]:
    """Compare effectiveness across prompt versions for a given slug."""
    prompts = db.select("prompts", filters={"slug": slug})
    if not prompts:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")
    prompt_id = prompts[0]["id"]

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = db.select("prompt_effectiveness")
    filtered = [
        r
        for r in rows
        if r.get("prompt_id") == str(prompt_id) and r.get("created_at", "") >= cutoff
    ]

    groups: dict[str, list[dict]] = {}
    for r in filtered:
        vid = str(r.get("version_id") or "unknown")
        groups.setdefault(vid, []).append(r)

    summaries = []
    for vid, records in groups.items():
        count = len(records)
        effs = [r.get("effectiveness") for r in records if r.get("effectiveness") is not None]
        scores = [r.get("outcome_score") for r in records if r.get("outcome_score") is not None]
        corrections = sum(r.get("correction_count", 0) for r in records)
        summaries.append(
            EffectivenessSummary(
                group_key="version_id",
                group_value=vid,
                session_count=count,
                avg_tokens=None,
                avg_cost_usd=None,
                avg_outcome_score=sum(scores) / len(scores) if scores else None,
                avg_effectiveness=sum(effs) / len(effs) if effs else None,
                total_corrections=corrections,
                correction_rate=corrections / count if count > 0 else None,
            )
        )
    return summaries


@router.get("/effectiveness/compression-candidates", response_model=list[dict[str, Any]])
async def compression_candidates() -> list[dict[str, Any]]:
    """Prompt versions flagged as verbose (>2x median tokens)."""
    from prompt_forge.core.analyser import analyse_verbose_prompts

    return await analyse_verbose_prompts()


@router.get("/effectiveness/autonomy-candidates", response_model=list[dict[str, Any]])
async def autonomy_candidates() -> list[dict[str, Any]]:
    """Agents where human intervention is low enough for autonomy expansion."""
    from prompt_forge.core.autonomy import analyse_autonomy_candidates

    return await analyse_autonomy_candidates()


@router.get("/effectiveness/mission/{mission_id}", response_model=dict[str, Any])
async def mission_cost_breakdown(
    mission_id: str,
    db: SupabaseClient = Depends(get_supabase_client),
) -> dict[str, Any]:
    """Planning + execution + review cost breakdown for a mission."""
    rows = db.select("prompt_effectiveness")
    mission_rows = [r for r in rows if r.get("mission_id") == mission_id]

    if not mission_rows:
        raise HTTPException(status_code=404, detail=f"No records for mission {mission_id}")

    total_cost = sum(r.get("cost_usd", 0) or 0 for r in mission_rows)
    total_tokens = sum(r.get("total_tokens", 0) or 0 for r in mission_rows)
    total_corrections = sum(r.get("correction_count", 0) or 0 for r in mission_rows)
    scores = [r["outcome_score"] for r in mission_rows if r.get("outcome_score") is not None]

    # Group by task_id to approximate stages.
    by_task: dict[str, list[dict]] = {}
    for r in mission_rows:
        tid = r.get("task_id") or "unattributed"
        by_task.setdefault(tid, []).append(r)

    stages = []
    for tid, records in by_task.items():
        stage_cost = sum(r.get("cost_usd", 0) or 0 for r in records)
        stage_tokens = sum(r.get("total_tokens", 0) or 0 for r in records)
        stages.append(
            {
                "task_id": tid,
                "cost_usd": stage_cost,
                "total_tokens": stage_tokens,
                "session_count": len(records),
            }
        )

    return {
        "mission_id": mission_id,
        "total_cost_usd": total_cost,
        "total_tokens": total_tokens,
        "total_corrections": total_corrections,
        "avg_outcome_score": sum(scores) / len(scores) if scores else None,
        "session_count": len(mission_rows),
        "stages": stages,
    }


@router.get("/effectiveness/discovery-accuracy", response_model=list[dict[str, Any]])
async def discovery_accuracy(
    days: int = Query(default=30, ge=1, le=365),
    db: SupabaseClient = Depends(get_supabase_client),
) -> list[dict[str, Any]]:
    """Initial vs post-discovery score comparison."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = db.select("prompt_effectiveness")
    filtered = [
        r
        for r in rows
        if r.get("created_at", "") >= cutoff
        and r.get("mission_id")
        and r.get("outcome_score") is not None
    ]

    missions: dict[str, list[dict]] = {}
    for r in filtered:
        mid = r["mission_id"]
        missions.setdefault(mid, []).append(r)

    results = []
    for mid, records in missions.items():
        sorted_recs = sorted(records, key=lambda x: x.get("created_at", ""))
        if len(sorted_recs) < 2:
            continue
        initial = sorted_recs[0].get("outcome_score", 0) or 0
        final = sorted_recs[-1].get("outcome_score", 0) or 0
        accuracy = 1 - abs(initial - final) / max(initial, 0.001) if initial > 0 else None
        results.append(
            {
                "mission_id": mid,
                "initial_score": initial,
                "final_score": final,
                "discovery_accuracy": accuracy,
                "session_count": len(sorted_recs),
            }
        )
    return results


def _row_to_response(row: dict) -> EffectivenessResponse:
    """Convert a database row to an EffectivenessResponse."""
    return EffectivenessResponse(
        id=row["id"],
        prompt_id=row.get("prompt_id"),
        version_id=row.get("version_id"),
        session_uuid=row["session_uuid"],
        mission_id=row.get("mission_id"),
        task_id=row.get("task_id"),
        agent_id=row["agent_id"],
        model_id=row["model_id"],
        model_tier=row.get("model_tier"),
        briefing_hash=row.get("briefing_hash"),
        input_tokens=row.get("input_tokens"),
        output_tokens=row.get("output_tokens"),
        total_tokens=row.get("total_tokens"),
        cost_usd=row.get("cost_usd"),
        correction_count=row.get("correction_count", 0),
        human_interventions=row.get("human_interventions", 0),
        outcome=row.get("outcome", "unknown"),
        outcome_score=row.get("outcome_score"),
        effectiveness=row.get("effectiveness"),
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
    )
