"""Prompt verbosity analyser — Feedback Loop 3.

Periodically analyses prompt_effectiveness data to identify prompt versions
that consume disproportionately many tokens relative to peers with similar
outcome scores. Flags verbose prompts and publishes NATS alerts.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from statistics import median

import structlog

from prompt_forge.db.client import get_supabase_client

logger = structlog.get_logger()


async def analyse_verbose_prompts() -> list[dict]:
    """Identify prompt versions using >2x median tokens with similar outcome.

    Returns a list of flagged version records with context.
    """
    db = get_supabase_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    rows = db.select("prompt_effectiveness")
    recent = [
        r
        for r in rows
        if r.get("created_at", "") >= cutoff and r.get("total_tokens") and r.get("version_id")
    ]

    if not recent:
        return []

    # Group by version_id.
    versions: dict[str, list[dict]] = {}
    for r in recent:
        vid = str(r["version_id"])
        versions.setdefault(vid, []).append(r)

    # Compute per-version averages.
    version_stats = []
    for vid, records in versions.items():
        tokens = [r["total_tokens"] for r in records]
        scores = [r["outcome_score"] for r in records if r.get("outcome_score") is not None]
        avg_tokens = sum(tokens) / len(tokens)
        avg_score = sum(scores) / len(scores) if scores else None
        version_stats.append(
            {
                "version_id": vid,
                "avg_tokens": avg_tokens,
                "avg_score": avg_score,
                "session_count": len(records),
                "prompt_id": records[0].get("prompt_id"),
            }
        )

    if len(version_stats) < 2:
        return []

    # Median token usage across all versions.
    all_avg_tokens = [v["avg_tokens"] for v in version_stats]
    median_tokens = median(all_avg_tokens)

    if median_tokens == 0:
        return []

    # Flag versions using >2x median tokens.
    flagged = []
    for v in version_stats:
        ratio = v["avg_tokens"] / median_tokens
        if ratio > 2.0:
            flagged.append(
                {
                    "version_id": v["version_id"],
                    "prompt_id": v["prompt_id"],
                    "avg_tokens": v["avg_tokens"],
                    "median_tokens": median_tokens,
                    "token_ratio": round(ratio, 2),
                    "avg_score": v["avg_score"],
                    "session_count": v["session_count"],
                }
            )

    return flagged


async def publish_verbose_alerts(flagged: list[dict]) -> int:
    """Publish swarm.prompt.verbose.detected for each flagged version."""
    if not flagged:
        return 0

    try:
        from prompt_forge.core.events import get_event_publisher

        publisher = get_event_publisher()
        if not publisher._connected:
            return 0
    except Exception:
        return 0

    published = 0
    for item in flagged:
        ok = await publisher.publish(
            event_type="prompt.verbose.detected",
            subject="swarm.prompt.verbose.detected",
            data=item,
        )
        if ok:
            published += 1

    return published


async def run_analyser_loop() -> None:
    """Background task: analyse verbose prompts every hour."""
    while True:
        try:
            await asyncio.sleep(3600)  # 1 hour
            flagged = await analyse_verbose_prompts()
            if flagged:
                published = await publish_verbose_alerts(flagged)
                logger.info(
                    "analyser.verbose_detected",
                    flagged=len(flagged),
                    published=published,
                )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("analyser.error", error=str(e))
