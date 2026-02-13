"""Usage logging and analytics endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from prompt_forge.api.models import UsageLogCreate, UsageLogResponse, UsageStatsResponse
from prompt_forge.db.client import SupabaseClient, get_supabase_client

router = APIRouter()


@router.post("", response_model=UsageLogResponse, status_code=201)
async def log_usage(
    data: UsageLogCreate,
    db: SupabaseClient = Depends(get_supabase_client),
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
    db: SupabaseClient = Depends(get_supabase_client),
) -> UsageStatsResponse:
    """Get usage statistics for a prompt."""
    prompts = db.select("prompts", filters={"slug": slug})
    if not prompts:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    prompt_id = prompts[0]["id"]
    logs = db.select("prompt_usage_log", filters={"prompt_id": prompt_id})

    total = len(logs)
    successes = sum(1 for entry in logs if entry.get("outcome") == "success")
    latencies = [entry["latency_ms"] for entry in logs if entry.get("latency_ms") is not None]

    version_counts: dict[str, int] = {}
    for entry in logs:
        vid = str(entry.get("version_id", "unknown"))
        version_counts[vid] = version_counts.get(vid, 0) + 1

    return UsageStatsResponse(
        prompt_slug=slug,
        total_uses=total,
        success_rate=successes / total if total > 0 else 0.0,
        avg_latency_ms=sum(latencies) / len(latencies) if latencies else None,
        version_breakdown=version_counts,
    )


@router.get("/stats")
async def all_usage_stats(
    db: SupabaseClient = Depends(get_supabase_client),
) -> list[dict[str, Any]]:
    """Aggregate stats per prompt (success rate, avg latency, usage count)."""
    logs = db.select("prompt_usage_log")
    prompts = db.select("prompts", filters={"archived": False})
    prompt_map = {p["id"]: p["slug"] for p in prompts}

    # Group by prompt
    by_prompt: dict[str, list[dict]] = {}
    for entry in logs:
        pid = entry.get("prompt_id")
        by_prompt.setdefault(pid, []).append(entry)

    results = []
    for pid, plogs in by_prompt.items():
        total = len(plogs)
        successes = sum(1 for entry in plogs if entry.get("outcome") == "success")
        latencies = [entry["latency_ms"] for entry in plogs if entry.get("latency_ms") is not None]
        results.append(
            {
                "prompt_id": pid,
                "prompt_slug": prompt_map.get(pid, "unknown"),
                "total_uses": total,
                "success_rate": round(successes / total, 3) if total else 0,
                "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
            }
        )

    return sorted(results, key=lambda r: r["total_uses"], reverse=True)


@router.get("/top")
async def top_prompts(
    limit: int = Query(default=10, le=100),
    db: SupabaseClient = Depends(get_supabase_client),
) -> list[dict[str, Any]]:
    """Most used prompts."""
    logs = db.select("prompt_usage_log")
    prompts = db.select("prompts", filters={"archived": False})
    prompt_map = {p["id"]: p for p in prompts}

    counts: dict[str, int] = {}
    for entry in logs:
        pid = entry.get("prompt_id")
        counts[pid] = counts.get(pid, 0) + 1

    top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    results = []
    for pid, count in top:
        p = prompt_map.get(pid, {})
        results.append(
            {
                "prompt_id": pid,
                "slug": p.get("slug", "unknown"),
                "name": p.get("name", "unknown"),
                "type": p.get("type", "unknown"),
                "usage_count": count,
            }
        )
    return results


@router.get("/performance")
async def version_performance(
    slug: str = Query(...),
    db: SupabaseClient = Depends(get_supabase_client),
) -> list[dict[str, Any]]:
    """Version performance comparison for a prompt."""
    prompts = db.select("prompts", filters={"slug": slug})
    if not prompts:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")

    prompt_id = prompts[0]["id"]
    logs = db.select("prompt_usage_log", filters={"prompt_id": prompt_id})
    versions = db.select("prompt_versions", filters={"prompt_id": prompt_id})
    version_map = {v["id"]: v["version"] for v in versions}

    # Group by version
    by_version: dict[str, list[dict]] = {}
    for entry in logs:
        vid = entry.get("version_id")
        by_version.setdefault(vid, []).append(entry)

    results = []
    for vid, vlogs in by_version.items():
        total = len(vlogs)
        successes = sum(1 for entry in vlogs if entry.get("outcome") == "success")
        failures = sum(1 for entry in vlogs if entry.get("outcome") == "failure")
        latencies = [entry["latency_ms"] for entry in vlogs if entry.get("latency_ms") is not None]
        results.append(
            {
                "version_id": vid,
                "version_number": version_map.get(vid, "?"),
                "total_uses": total,
                "successes": successes,
                "failures": failures,
                "success_rate": round(successes / total, 3) if total else 0,
                "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
            }
        )

    return sorted(results, key=lambda r: r.get("version_number", 0))
