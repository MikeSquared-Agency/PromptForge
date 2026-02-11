"""Usage logging and analytics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from prompt_forge.api.models import UsageLogCreate, UsageLogResponse, UsageStatsResponse
from prompt_forge.db.client import SupabaseClient, get_supabase_client

router = APIRouter()


def _get_db() -> SupabaseClient:
    return get_supabase_client()


@router.post("", response_model=UsageLogResponse, status_code=201)
async def log_usage(
    data: UsageLogCreate,
    db: SupabaseClient = Depends(_get_db),
) -> UsageLogResponse:
    """Log a prompt usage event."""
    record = db.insert(
        "prompt_usage_log",
        {
            "prompt_id": str(data.prompt_id),
            "version_id": str(data.version_id),
            "agent_id": data.agent_id,
            "composition_manifest": data.composition_manifest,
            "outcome": data.outcome,
            "latency_ms": data.latency_ms,
            "feedback": data.feedback,
        },
    )
    return UsageLogResponse(**record)


@router.get("/stats/{slug}", response_model=UsageStatsResponse)
async def usage_stats(
    slug: str,
    db: SupabaseClient = Depends(_get_db),
) -> UsageStatsResponse:
    """Get usage statistics for a prompt."""
    # Look up prompt by slug
    prompts = db.select("prompts", filters={"slug": slug})
    if not prompts:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    prompt_id = prompts[0]["id"]
    logs = db.select("prompt_usage_log", filters={"prompt_id": prompt_id})

    total = len(logs)
    successes = sum(1 for l in logs if l.get("outcome") == "success")
    latencies = [l["latency_ms"] for l in logs if l.get("latency_ms") is not None]

    # Version breakdown
    version_counts: dict[str, int] = {}
    for l in logs:
        vid = str(l.get("version_id", "unknown"))
        version_counts[vid] = version_counts.get(vid, 0) + 1

    return UsageStatsResponse(
        prompt_slug=slug,
        total_uses=total,
        success_rate=successes / total if total > 0 else 0.0,
        avg_latency_ms=sum(latencies) / len(latencies) if latencies else None,
        version_breakdown=version_counts,
    )
