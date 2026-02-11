"""Test fixtures — mock Supabase client and shared test data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from prompt_forge.db.client import SupabaseClient


class MockSupabaseClient(SupabaseClient):
    """In-memory mock of the Supabase client for testing."""

    def __init__(self):
        self._tables: dict[str, list[dict[str, Any]]] = {
            "prompts": [],
            "prompt_versions": [],
            "prompt_branches": [],
            "prompt_usage_log": [],
            "audit_log": [],
        }

    @property
    def client(self):
        return MagicMock()

    def insert(self, table: str, data: dict[str, Any]) -> dict[str, Any]:
        record = {
            "id": str(uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        self._tables.setdefault(table, []).append(record)
        return record

    def select(
        self,
        table: str,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        ascending: bool = True,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._tables.get(table, [])
        if filters:
            for key, value in filters.items():
                rows = [r for r in rows if r.get(key) == value]
        if order_by:
            rows = sorted(rows, key=lambda r: r.get(order_by, 0), reverse=not ascending)
        if limit:
            rows = rows[:limit]
        return rows

    def update(self, table: str, id: str, data: dict[str, Any]) -> dict[str, Any]:
        for row in self._tables.get(table, []):
            if row["id"] == id:
                row.update(data)
                row["updated_at"] = datetime.now(timezone.utc).isoformat()
                return row
        raise ValueError(f"Row {id} not found in {table}")

    def delete(self, table: str, id: str) -> None:
        self._tables[table] = [r for r in self._tables.get(table, []) if r["id"] != id]

    def reset(self):
        for table in self._tables:
            self._tables[table] = []


@pytest.fixture
def mock_db() -> MockSupabaseClient:
    """Fresh mock database for each test."""
    return MockSupabaseClient()


@pytest.fixture
def sample_content() -> dict[str, Any]:
    """Sample prompt content."""
    return {
        "sections": [
            {"id": "identity", "label": "Identity", "content": "You are a senior code reviewer."},
            {"id": "skills", "label": "Skills", "content": "You excel at Python and security."},
            {"id": "constraints", "label": "Constraints", "content": "Be concise."},
        ],
        "variables": {"project_name": "{{project_name}}"},
        "metadata": {"estimated_tokens": 50},
    }


@pytest.fixture
def app(mock_db):
    """FastAPI test app with mocked dependencies."""
    from prompt_forge.core.audit import AuditLogger
    from prompt_forge.core.composer import CompositionEngine
    from prompt_forge.core.registry import PromptRegistry
    from prompt_forge.core.resolver import PromptResolver
    from prompt_forge.core.vcs import VersionControl
    from prompt_forge.main import app as _app

    registry = PromptRegistry(mock_db)
    vcs = VersionControl(mock_db)
    resolver = PromptResolver(mock_db)
    composer = CompositionEngine(resolver, registry)
    audit = AuditLogger(mock_db)

    # Override dependencies
    from prompt_forge.core.audit import get_audit_logger
    from prompt_forge.core.registry import get_registry
    from prompt_forge.core.vcs import get_vcs
    from prompt_forge.core.resolver import get_resolver
    from prompt_forge.core.composer import get_composer
    from prompt_forge.db.client import get_supabase_client

    _app.dependency_overrides[get_registry] = lambda: registry
    _app.dependency_overrides[get_vcs] = lambda: vcs
    _app.dependency_overrides[get_resolver] = lambda: resolver
    _app.dependency_overrides[get_composer] = lambda: composer
    _app.dependency_overrides[get_supabase_client] = lambda: mock_db
    _app.dependency_overrides[get_audit_logger] = lambda: audit

    yield _app

    _app.dependency_overrides.clear()


@pytest.fixture
def client(app) -> TestClient:
    """HTTP test client."""
    return TestClient(app)
