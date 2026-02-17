"""A/B experiment CRUD and evaluation endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from prompt_forge.db.client import SupabaseClient, get_supabase_client

logger = structlog.get_logger()
router = APIRouter()


# ── Request / Response models ────────────────────────────────────────

class ExperimentCreate(BaseModel):
    prompt_slug: str
    control_version: str
    variant_version: str
    split_pct: int = Field(default=50, ge=1, le=99)
    min_sessions: int = Field(default=50, ge=1)
    max_duration_d: int = Field(default=14, ge=1)


class ExperimentConclude(BaseModel):
    conclusion: str = Field(..., pattern="^(promoted|rejected)$")


# ── CRUD ─────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_experiment(
    data: ExperimentCreate,
    db: SupabaseClient = Depends(get_supabase_client),
):
    """Create a new A/B experiment."""
    row = db.insert("experiments", data.model_dump())
    return row


@router.get("")
async def list_experiments(
    status: Optional[str] = Query(default=None),
    db: SupabaseClient = Depends(get_supabase_client),
):
    """List experiments, optionally filtered by status."""
    filters = {}
    if status:
        filters["status"] = status
    return db.select("experiments", filters=filters or None, order_by="created_at", ascending=False)


@router.get("/{experiment_id}")
async def get_experiment(
    experiment_id: str,
    db: SupabaseClient = Depends(get_supabase_client),
):
    """Get a single experiment by ID."""
    rows = db.select("experiments", filters={"id": experiment_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return rows[0]


@router.post("/{experiment_id}/pause")
async def pause_experiment(
    experiment_id: str,
    db: SupabaseClient = Depends(get_supabase_client),
):
    """Pause a running experiment."""
    rows = db.select("experiments", filters={"id": experiment_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if rows[0]["status"] != "running":
        raise HTTPException(status_code=409, detail="Experiment is not running")
    return db.update("experiments", experiment_id, {"status": "paused"})


@router.post("/{experiment_id}/resume")
async def resume_experiment(
    experiment_id: str,
    db: SupabaseClient = Depends(get_supabase_client),
):
    """Resume a paused experiment."""
    rows = db.select("experiments", filters={"id": experiment_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if rows[0]["status"] != "paused":
        raise HTTPException(status_code=409, detail="Experiment is not paused")
    return db.update("experiments", experiment_id, {"status": "running"})


@router.post("/{experiment_id}/conclude")
async def conclude_experiment(
    experiment_id: str,
    data: ExperimentConclude,
    db: SupabaseClient = Depends(get_supabase_client),
):
    """Conclude an experiment with a decision."""
    rows = db.select("experiments", filters={"id": experiment_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if rows[0]["status"] == "concluded":
        raise HTTPException(status_code=409, detail="Experiment already concluded")
    now = datetime.now(timezone.utc).isoformat()
    return db.update("experiments", experiment_id, {
        "status": "concluded",
        "conclusion": data.conclusion,
        "concluded_at": now,
    })


# ── Evaluation / Results ─────────────────────────────────────────────

@router.get("/{experiment_id}/results")
async def get_experiment_results(
    experiment_id: str,
    db: SupabaseClient = Depends(get_supabase_client),
):
    """Get current experiment stats (assignment counts per arm)."""
    rows = db.select("experiments", filters={"id": experiment_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Experiment not found")

    experiment = rows[0]

    # Auto-expire check
    created_at = datetime.fromisoformat(experiment["created_at"].replace("Z", "+00:00"))
    days_running = (datetime.now(timezone.utc) - created_at).days

    if experiment["status"] == "running" and days_running > experiment["max_duration_d"]:
        now = datetime.now(timezone.utc).isoformat()
        experiment = db.update("experiments", experiment_id, {
            "status": "concluded",
            "conclusion": "expired",
            "concluded_at": now,
        })
        logger.info("experiment.auto_expired", experiment_id=experiment_id, days=days_running)

    # Count assignments per arm
    assignments = db.select("experiment_assignments", filters={"experiment_id": experiment_id})
    control_count = sum(1 for a in assignments if a["arm"] == "control")
    variant_count = sum(1 for a in assignments if a["arm"] == "variant")

    return {
        "experiment_id": experiment_id,
        "status": experiment["status"],
        "conclusion": experiment.get("conclusion"),
        "days_running": days_running,
        "control_count": control_count,
        "variant_count": variant_count,
    }
