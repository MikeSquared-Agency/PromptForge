"""Subscription endpoints for prompt change notifications."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from prompt_forge.core.registry import PromptRegistry, get_registry
from prompt_forge.db.client import SupabaseClient, get_supabase_client

router = APIRouter()


class SubscriptionResponse(BaseModel):
    id: str
    prompt_id: str
    agent_id: str
    subscribed_at: str
    last_pulled_at: str


class SubscriberResponse(BaseModel):
    agent_id: str
    subscribed_at: str
    last_pulled_at: str


class AgentSubscriptionResponse(BaseModel):
    prompt_id: str
    prompt_slug: str
    subscribed_at: str
    last_pulled_at: str


def _get_prompt_or_404(slug: str, registry: PromptRegistry) -> dict[str, Any]:
    prompt = registry.get_prompt(slug)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{slug}' not found")
    return prompt


@router.post("/{slug}/subscribe", response_model=SubscriptionResponse, status_code=201)
async def subscribe(
    slug: str,
    x_agent_id: str = Header(..., alias="X-Agent-ID"),
    registry: PromptRegistry = Depends(get_registry),
    db: SupabaseClient = Depends(get_supabase_client),
) -> SubscriptionResponse:
    prompt = _get_prompt_or_404(slug, registry)
    # Upsert
    existing = [
        r
        for r in db.select("prompt_subscriptions", filters={"prompt_id": prompt["id"]})
        if r["agent_id"] == x_agent_id
    ]
    if existing:
        updated = db.update(
            "prompt_subscriptions",
            existing[0]["id"],
            {
                "last_pulled_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return SubscriptionResponse(
            id=str(updated["id"]),
            prompt_id=str(updated["prompt_id"]),
            agent_id=updated["agent_id"],
            subscribed_at=str(updated.get("subscribed_at", updated.get("created_at", ""))),
            last_pulled_at=str(updated.get("last_pulled_at", updated.get("created_at", ""))),
        )

    sub = db.insert(
        "prompt_subscriptions",
        {
            "prompt_id": prompt["id"],
            "agent_id": x_agent_id,
        },
    )
    return SubscriptionResponse(
        id=str(sub["id"]),
        prompt_id=str(sub["prompt_id"]),
        agent_id=sub["agent_id"],
        subscribed_at=sub.get("subscribed_at", sub.get("created_at", "")),
        last_pulled_at=sub.get("last_pulled_at", sub.get("created_at", "")),
    )


@router.delete("/{slug}/subscribe", status_code=204)
async def unsubscribe(
    slug: str,
    x_agent_id: str = Header(..., alias="X-Agent-ID"),
    registry: PromptRegistry = Depends(get_registry),
    db: SupabaseClient = Depends(get_supabase_client),
) -> None:
    prompt = _get_prompt_or_404(slug, registry)
    existing = [
        r
        for r in db.select("prompt_subscriptions", filters={"prompt_id": prompt["id"]})
        if r["agent_id"] == x_agent_id
    ]
    if not existing:
        raise HTTPException(status_code=404, detail="Subscription not found")
    db.delete("prompt_subscriptions", existing[0]["id"])


@router.get("/{slug}/subscribers", response_model=list[SubscriberResponse])
async def list_subscribers(
    slug: str,
    registry: PromptRegistry = Depends(get_registry),
    db: SupabaseClient = Depends(get_supabase_client),
) -> list[SubscriberResponse]:
    prompt = _get_prompt_or_404(slug, registry)
    subs = db.select("prompt_subscriptions", filters={"prompt_id": prompt["id"]})
    return [
        SubscriberResponse(
            agent_id=s["agent_id"],
            subscribed_at=str(s.get("subscribed_at", s.get("created_at", ""))),
            last_pulled_at=str(s.get("last_pulled_at", s.get("created_at", ""))),
        )
        for s in subs
    ]
