"""Autonomy expansion analyser — Feedback Loop 4.

Analyses human intervention patterns to identify gates where agent
recommendations align with human decisions >90% of the time, flagging
them as candidates for increased autonomy.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog

from prompt_forge.db.client import get_supabase_client

logger = structlog.get_logger()


async def analyse_autonomy_candidates() -> list[dict]:
    """Identify agents/gate types where human interventions are low enough
    to consider expanding autonomy.

    Uses a rolling 30-day window. An agent is a candidate if:
    - At least 10 completed sessions
    - human_interventions == 0 in >90% of sessions (agent recommendation accepted)
    """
    db = get_supabase_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    rows = db.select("prompt_effectiveness")
    recent = [
        r
        for r in rows
        if r.get("created_at", "") >= cutoff and r.get("completed_at") and r.get("agent_id")
    ]

    if not recent:
        return []

    # Group by agent_id.
    agents: dict[str, list[dict]] = {}
    for r in recent:
        aid = r["agent_id"]
        agents.setdefault(aid, []).append(r)

    candidates = []
    for aid, records in agents.items():
        if len(records) < 10:
            continue

        total = len(records)
        no_intervention = sum(1 for r in records if (r.get("human_interventions") or 0) == 0)
        alignment_rate = no_intervention / total

        if alignment_rate >= 0.9:
            avg_score = None
            scores = [r["outcome_score"] for r in records if r.get("outcome_score") is not None]
            if scores:
                avg_score = sum(scores) / len(scores)

            candidates.append(
                {
                    "agent_id": aid,
                    "session_count": total,
                    "no_intervention_count": no_intervention,
                    "alignment_rate": round(alignment_rate, 4),
                    "avg_outcome_score": round(avg_score, 4) if avg_score is not None else None,
                }
            )

    return candidates


async def publish_autonomy_alerts(candidates: list[dict]) -> int:
    """Publish swarm.prompt.autonomy.candidate for each candidate."""
    if not candidates:
        return 0

    try:
        from prompt_forge.core.events import get_event_publisher

        publisher = get_event_publisher()
        if not publisher._connected:
            return 0
    except Exception:
        return 0

    published = 0
    for item in candidates:
        ok = await publisher.publish(
            event_type="prompt.autonomy.candidate",
            subject="swarm.prompt.autonomy.candidate",
            data=item,
        )
        if ok:
            published += 1

    return published


async def run_autonomy_loop() -> None:
    """Background task: analyse autonomy candidates every hour."""
    while True:
        try:
            await asyncio.sleep(3600)  # 1 hour
            candidates = await analyse_autonomy_candidates()
            if candidates:
                published = await publish_autonomy_alerts(candidates)
                logger.info(
                    "autonomy.candidates_detected",
                    candidates=len(candidates),
                    published=published,
                )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("autonomy.error", error=str(e))
