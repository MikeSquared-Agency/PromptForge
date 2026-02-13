"""Agent-centric endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from prompt_forge.db.client import SupabaseClient, get_supabase_client

router = APIRouter()


class AgentSubscriptionResponse(BaseModel):
    prompt_id: str
    prompt_slug: str
    subscribed_at: str
    last_pulled_at: str


@router.get("/{agent_id}/subscriptions", response_model=list[AgentSubscriptionResponse])
async def list_agent_subscriptions(
    agent_id: str,
    db: SupabaseClient = Depends(get_supabase_client),
) -> list[AgentSubscriptionResponse]:
    subs = [r for r in db.select("prompt_subscriptions") if r["agent_id"] == agent_id]
    # Look up prompt slugs
    result = []
    for s in subs:
        prompts = db.select("prompts", filters={"id": s["prompt_id"]})
        slug = prompts[0]["slug"] if prompts else "unknown"
        result.append(
            AgentSubscriptionResponse(
                prompt_id=str(s["prompt_id"]),
                prompt_slug=slug,
                subscribed_at=str(s.get("subscribed_at", s.get("created_at", ""))),
                last_pulled_at=str(s.get("last_pulled_at", s.get("created_at", ""))),
            )
        )
    return result
