"""Pydantic request/response models for the API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# --- Prompts ---

class PromptCreate(BaseModel):
    """Create a new prompt."""
    slug: str = Field(..., pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", min_length=2, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field(..., pattern=r"^(persona|skill|constraint|template|meta)$")
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content: dict[str, Any] | None = None
    initial_message: str = "Initial version"
    parent_slug: str | None = None
    subscriber_count: int = 0


class PromptUpdate(BaseModel):
    """Update a prompt's metadata."""
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class PromptResponse(BaseModel):
    """Prompt response."""
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
    parent_slug: str | None = None
    subscriber_count: int = 0


# --- Versions ---

class VersionCreate(BaseModel):
    """Create a new version (commit)."""
    content: dict[str, Any]
    message: str = "Update"
    author: str = "system"
    branch: str = "main"
    override_sections: dict[str, Any] | None = None
    priority: str = "normal"
    acknowledge_reduction: bool = False


class VersionPatch(BaseModel):
    """Partial version update — merges into latest version's content."""
    content: dict[str, Any]
    message: str = "Update"
    author: str = "system"
    branch: str = "main"
    priority: str = "normal"
    acknowledge_reduction: bool = False


class VersionRestoreRequest(BaseModel):
    """Restore a historical version, optionally merging with a patch."""
    from_version: int
    patch: dict[str, Any] | None = None
    message: str | None = None
    author: str = "system"
    branch: str = "main"
    priority: str = "normal"
    acknowledge_reduction: bool = False


class RegressionWarning(BaseModel):
    """A single regression warning."""
    type: str
    detail: Any
    message: str


class VersionResponse(BaseModel):
    """Version response."""
    id: UUID
    prompt_id: UUID
    version: int
    content: dict[str, Any]
    message: str
    author: str
    parent_version_id: UUID | None
    branch: str
    created_at: datetime
    warnings: list[RegressionWarning] | None = None


class DiffResponse(BaseModel):
    """Structural diff between two versions (section-level)."""
    prompt_id: UUID
    from_version: int
    to_version: int
    changes: list[dict[str, Any]]
    summary: str


class FieldDiffResponse(BaseModel):
    """Field-level diff between two versions (top-level keys)."""
    from_version: int
    to_version: int
    changes: list[dict[str, Any]]
    summary: dict[str, Any]


class RollbackRequest(BaseModel):
    """Rollback to a specific version."""
    version: int
    author: str = "system"


# --- Composition ---

class ComposeRequest(BaseModel):
    """Compose an agent prompt from components."""
    persona: str
    skills: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    variables: dict[str, str] = Field(default_factory=dict)
    branch: str = "main"
    strategy: str = "latest"


class ComponentManifest(BaseModel):
    """Record of a single component used in composition."""
    slug: str
    type: str
    version: int
    branch: str


class CompositionManifest(BaseModel):
    """Full provenance record for a composed prompt."""
    composed_at: datetime
    components: list[ComponentManifest]
    variables_applied: dict[str, str]
    estimated_tokens: int


class ComposeResponse(BaseModel):
    """Composition result."""
    prompt: str
    manifest: CompositionManifest
    warnings: list[str] = Field(default_factory=list)


class ResolveRequest(BaseModel):
    """Resolve a single prompt component."""
    slug: str
    branch: str = "main"
    version: int | None = None
    strategy: str = "latest"


# --- Usage ---

# --- Scanning ---

class ScanRequest(BaseModel):
    """Scan content for injection attempts."""
    content: dict[str, Any]
    sensitivity: str = "normal"


class FindingResponse(BaseModel):
    """A single scan finding."""
    pattern_name: str
    matched_text: str
    location: str
    severity: str
    description: str


class ScanResponse(BaseModel):
    """Scan result."""
    clean: bool
    findings: list[FindingResponse] = Field(default_factory=list)
    risk_level: str


# --- Audit ---

class AuditEntryResponse(BaseModel):
    """Audit log entry."""
    id: UUID
    action: str
    entity_type: str
    entity_id: UUID | None
    actor: str
    details: dict[str, Any]
    ip_address: str | None
    created_at: datetime


# --- Usage ---

class UsageLogCreate(BaseModel):
    """Log a usage event."""
    prompt_id: UUID
    version_id: UUID
    agent_id: str
    composition_manifest: dict[str, Any] | None = None
    outcome: str = Field(default="unknown", pattern=r"^(success|failure|partial|unknown)$")
    latency_ms: int | None = None
    feedback: dict[str, Any] | None = None


class UsageLogResponse(BaseModel):
    """Usage log entry."""
    id: UUID
    prompt_id: UUID
    version_id: UUID
    agent_id: str
    composition_manifest: dict[str, Any] | None
    resolved_at: datetime
    outcome: str
    latency_ms: int | None
    feedback: dict[str, Any] | None


class UsageStatsResponse(BaseModel):
    """Usage statistics for a prompt."""
    prompt_slug: str
    total_uses: int
    success_rate: float
    avg_latency_ms: float | None
    version_breakdown: dict[str, int]
