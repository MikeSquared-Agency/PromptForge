"""Audit log endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from prompt_forge.api.models import AuditEntryResponse
from prompt_forge.core.audit import AuditLogger, get_audit_logger

router = APIRouter()


@router.get("/audit", response_model=list[AuditEntryResponse])
async def query_audit_log(
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor: str | None = None,
    action: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = Query(default=50, le=200),
    audit: AuditLogger = Depends(get_audit_logger),
) -> list[AuditEntryResponse]:
    """Query audit log with filters."""
    entries = audit.query(
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        action=action,
        since=since,
        until=until,
        limit=limit,
    )
    return [
        AuditEntryResponse(
            id=e.id,
            action=e.action,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            actor=e.actor,
            details=e.details,
            ip_address=e.ip_address,
            created_at=e.created_at,
        )
        for e in entries
    ]


@router.get("/audit/{entity_type}/{entity_id}", response_model=list[AuditEntryResponse])
async def audit_entity(
    entity_type: str,
    entity_id: str,
    limit: int = Query(default=50, le=200),
    audit: AuditLogger = Depends(get_audit_logger),
) -> list[AuditEntryResponse]:
    """Get audit trail for a specific entity."""
    entries = audit.query(entity_type=entity_type, entity_id=entity_id, limit=limit)
    return [
        AuditEntryResponse(
            id=e.id,
            action=e.action,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            actor=e.actor,
            details=e.details,
            ip_address=e.ip_address,
            created_at=e.created_at,
        )
        for e in entries
    ]
