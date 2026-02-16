"""Database models / type definitions.

These mirror the Supabase tables for type safety in Python code.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class PromptRow(BaseModel):
    """Row from the prompts table."""

    id: UUID
    slug: str
    name: str
    type: str
    description: str
    tags: list[str]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    archived: bool


class VersionRow(BaseModel):
    """Row from the prompt_versions table."""

    id: UUID
    prompt_id: UUID
    version: int
    content: dict[str, Any]
    message: str
    author: str
    parent_version_id: UUID | None
    branch: str
    created_at: datetime


class BranchRow(BaseModel):
    """Row from the prompt_branches table."""

    id: UUID
    prompt_id: UUID
    name: str
    head_version_id: UUID | None
    base_version_id: UUID | None
    status: str
    created_at: datetime
    updated_at: datetime


class UsageLogRow(BaseModel):
    """Row from the prompt_usage_log table."""

    id: UUID
    prompt_id: UUID
    version_id: UUID
    agent_id: str
    composition_manifest: dict[str, Any] | None
    resolved_at: datetime
    outcome: str
    latency_ms: int | None
    feedback: dict[str, Any] | None


class PersonaPromptRow(BaseModel):
    """Row from the persona_prompts table."""

    id: UUID
    persona: str
    version: int
    template: str
    is_latest: bool
    created_at: datetime
