"""Tests for audit logging."""

from __future__ import annotations

import pytest

from prompt_forge.core.audit import AuditLogger
from tests.conftest import MockSupabaseClient


@pytest.fixture
def db():
    return MockSupabaseClient()


@pytest.fixture
def audit(db):
    return AuditLogger(db)


class TestAuditLogging:
    def test_log_creates_entry(self, audit):
        entry = audit.log(
            action="prompt.created",
            entity_type="prompt",
            entity_id="some-uuid",
            actor="test-user",
            details={"slug": "test-prompt"},
        )
        assert entry["action"] == "prompt.created"
        assert entry["actor"] == "test-user"
        assert entry["details"]["slug"] == "test-prompt"

    def test_query_returns_entries(self, audit):
        audit.log("prompt.created", "prompt", "id1", "user1")
        audit.log("prompt.updated", "prompt", "id1", "user1")
        audit.log("version.committed", "version", "id2", "user2")

        entries = audit.query()
        assert len(entries) == 3

    def test_query_filter_by_action(self, audit):
        audit.log("prompt.created", "prompt", "id1", "user1")
        audit.log("version.committed", "version", "id2", "user2")

        entries = audit.query(action="prompt.created")
        assert len(entries) == 1
        assert entries[0].action == "prompt.created"

    def test_query_filter_by_actor(self, audit):
        audit.log("prompt.created", "prompt", "id1", "alice")
        audit.log("prompt.created", "prompt", "id2", "bob")

        entries = audit.query(actor="alice")
        assert len(entries) == 1
        assert entries[0].actor == "alice"

    def test_query_filter_by_entity(self, audit):
        audit.log("prompt.created", "prompt", "id1", "user1")
        audit.log("version.committed", "version", "id2", "user1")

        entries = audit.query(entity_type="prompt")
        assert len(entries) == 1

    def test_query_filter_by_entity_id(self, audit):
        audit.log("prompt.created", "prompt", "id1", "user1")
        audit.log("prompt.updated", "prompt", "id1", "user1")
        audit.log("prompt.created", "prompt", "id2", "user1")

        entries = audit.query(entity_id="id1")
        assert len(entries) == 2

    def test_query_limit(self, audit):
        for i in range(10):
            audit.log(f"action.{i}", "prompt", f"id{i}", "user1")

        entries = audit.query(limit=3)
        assert len(entries) == 3

    def test_entry_contains_details(self, audit):
        audit.log(
            "version.committed",
            "version",
            "ver-id",
            "agent-x",
            details={"version": 3, "branch": "main", "message": "fix typo"},
        )

        entries = audit.query(action="version.committed")
        assert entries[0].details["version"] == 3
        assert entries[0].details["branch"] == "main"

    def test_log_with_ip_address(self, audit):
        audit.log("prompt.created", "prompt", "id1", "user1", ip_address="192.168.1.1")
        entries = audit.query()
        assert entries[0].ip_address == "192.168.1.1"


class TestAuditAPI:
    def test_audit_endpoint(self, client):
        """GET /api/v1/audit returns entries."""
        resp = client.get("/api/v1/audit")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_audit_entity_endpoint(self, client):
        """GET /api/v1/audit/{type}/{id} returns entity trail."""
        resp = client.get("/api/v1/audit/prompt/some-id")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
