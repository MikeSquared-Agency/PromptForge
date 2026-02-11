"""Audit Logger — tracks all mutations for compliance and debugging."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import structlog

from prompt_forge.db.client import SupabaseClient, get_supabase_client

logger = structlog.get_logger()


@dataclass
class AuditEntry:
    """An audit log entry."""
    id: str
    action: str
    entity_type: str
    entity_id: str | None
    actor: str
    details: dict[str, Any]
    ip_address: str | None
    created_at: str


class AuditLogger:
    """Logs and queries audit trail entries."""

    def __init__(self, db: SupabaseClient) -> None:
        self.db = db

    def log(
        self,
        action: str,
        entity_type: str,
        entity_id: str | None = None,
        actor: str = "system",
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        """Create an audit log entry."""
        entry = self.db.insert(
            "audit_log",
            {
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "actor": actor,
                "details": details or {},
                "ip_address": ip_address,
            },
        )
        logger.info("audit.logged", action=action, entity_type=entity_type, actor=actor)
        return entry

    def query(
        self,
        entity_type: str | None = None,
        entity_id: str | None = None,
        actor: str | None = None,
        action: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 50,
    ) -> list[AuditEntry]:
        """Query audit log with filters."""
        filters: dict[str, Any] = {}
        if entity_type:
            filters["entity_type"] = entity_type
        if entity_id:
            filters["entity_id"] = entity_id
        if actor:
            filters["actor"] = actor
        if action:
            filters["action"] = action

        rows = self.db.select(
            "audit_log",
            filters=filters if filters else None,
            order_by="created_at",
            ascending=False,
            limit=limit,
        )

        # Client-side time filtering
        entries = []
        for row in rows:
            created = row.get("created_at", "")
            if since and created < since:
                continue
            if until and created > until:
                continue
            entries.append(AuditEntry(
                id=row["id"],
                action=row["action"],
                entity_type=row["entity_type"],
                entity_id=row.get("entity_id"),
                actor=row["actor"],
                details=row.get("details", {}),
                ip_address=row.get("ip_address"),
                created_at=created,
            ))

        return entries[:limit]


@lru_cache
def get_audit_logger() -> AuditLogger:
    """Get cached audit logger instance."""
    return AuditLogger(get_supabase_client())
