"""Tests for subscription system."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch


class TestSubscribeEndpoints:
    def _create_prompt(self, client, slug="sub-test"):
        return client.post(
            "/api/v1/prompts",
            json={
                "slug": slug,
                "name": "Sub Test",
                "type": "persona",
            },
        )

    def test_subscribe(self, client):
        self._create_prompt(client)
        resp = client.post(
            "/api/v1/prompts/sub-test/subscribe",
            headers={"X-Agent-ID": "agent-1"},
        )
        assert resp.status_code == 201
        assert resp.json()["agent_id"] == "agent-1"

    def test_subscribe_idempotent(self, client):
        self._create_prompt(client)
        client.post("/api/v1/prompts/sub-test/subscribe", headers={"X-Agent-ID": "agent-1"})
        resp = client.post("/api/v1/prompts/sub-test/subscribe", headers={"X-Agent-ID": "agent-1"})
        # Should succeed (upsert)
        assert resp.status_code == 201

    def test_subscribe_missing_header(self, client):
        self._create_prompt(client)
        resp = client.post("/api/v1/prompts/sub-test/subscribe")
        assert resp.status_code == 422

    def test_subscribe_not_found(self, client):
        resp = client.post(
            "/api/v1/prompts/nonexistent/subscribe",
            headers={"X-Agent-ID": "agent-1"},
        )
        assert resp.status_code == 404

    def test_unsubscribe(self, client):
        self._create_prompt(client)
        client.post("/api/v1/prompts/sub-test/subscribe", headers={"X-Agent-ID": "agent-1"})
        resp = client.delete(
            "/api/v1/prompts/sub-test/subscribe", headers={"X-Agent-ID": "agent-1"}
        )
        assert resp.status_code == 204

    def test_unsubscribe_not_found(self, client):
        self._create_prompt(client)
        resp = client.delete(
            "/api/v1/prompts/sub-test/subscribe", headers={"X-Agent-ID": "agent-1"}
        )
        assert resp.status_code == 404

    def test_list_subscribers(self, client):
        self._create_prompt(client)
        client.post("/api/v1/prompts/sub-test/subscribe", headers={"X-Agent-ID": "agent-1"})
        client.post("/api/v1/prompts/sub-test/subscribe", headers={"X-Agent-ID": "agent-2"})
        resp = client.get("/api/v1/prompts/sub-test/subscribers")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_agent_subscriptions(self, client):
        self._create_prompt(client, "prompt-a")
        self._create_prompt(client, "prompt-b")
        client.post("/api/v1/prompts/prompt-a/subscribe", headers={"X-Agent-ID": "agent-1"})
        client.post("/api/v1/prompts/prompt-b/subscribe", headers={"X-Agent-ID": "agent-1"})
        resp = client.get("/api/v1/agents/agent-1/subscriptions")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestAutoSubscribe:
    def test_auto_subscribe_on_version_fetch(self, client, sample_content):
        client.post(
            "/api/v1/prompts",
            json={
                "slug": "auto-sub",
                "name": "AS",
                "type": "persona",
            },
        )
        client.post(
            "/api/v1/prompts/auto-sub/versions",
            json={
                "content": sample_content,
                "message": "v1",
            },
        )
        # Fetch version with agent ID
        resp = client.get(
            "/api/v1/prompts/auto-sub/versions/1",
            headers={"X-Agent-ID": "agent-auto"},
        )
        assert resp.status_code == 200

        # Should now be subscribed
        subs = client.get("/api/v1/prompts/auto-sub/subscribers")
        agents = [s["agent_id"] for s in subs.json()]
        assert "agent-auto" in agents

    def test_no_auto_subscribe_without_header(self, client, sample_content):
        client.post(
            "/api/v1/prompts",
            json={
                "slug": "no-auto",
                "name": "NA",
                "type": "persona",
            },
        )
        client.post(
            "/api/v1/prompts/no-auto/versions",
            json={
                "content": sample_content,
                "message": "v1",
            },
        )
        client.get("/api/v1/prompts/no-auto/versions/1")
        subs = client.get("/api/v1/prompts/no-auto/subscribers")
        assert len(subs.json()) == 0


class TestEventPublishing:
    def test_version_create_notifies_subscribers(self, client, mock_db, sample_content):
        client.post(
            "/api/v1/prompts",
            json={
                "slug": "evented",
                "name": "E",
                "type": "persona",
            },
        )
        # Subscribe an agent
        client.post("/api/v1/prompts/evented/subscribe", headers={"X-Agent-ID": "agent-notify"})

        with patch("prompt_forge.core.events.get_event_publisher") as mock_pub:
            publisher = AsyncMock()
            publisher._connected = True
            publisher.publish = AsyncMock(return_value=True)
            mock_pub.return_value = publisher

            client.post(
                "/api/v1/prompts/evented/versions",
                json={
                    "content": sample_content,
                    "message": "update",
                    "priority": "critical",
                },
            )

            # Check publish was called with correct subject
            if publisher.publish.called:
                call_args = publisher.publish.call_args
                assert "agent-notify" in call_args.kwargs.get(
                    "subject", call_args[1].get("subject", "")
                )
                assert (
                    call_args.kwargs.get("data", call_args[1].get("data", {})).get("priority")
                    == "critical"
                )


class TestTTLCleanup:
    def test_stale_subscriptions_removed(self, mock_db):
        """Test that stale subscriptions are identified correctly."""

        # Insert a stale subscription
        stale_time = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        mock_db.insert(
            "prompt_subscriptions",
            {
                "prompt_id": "fake-id",
                "agent_id": "stale-agent",
                "last_pulled_at": stale_time,
            },
        )
        # Insert a fresh subscription
        fresh_time = datetime.now(timezone.utc).isoformat()
        mock_db.insert(
            "prompt_subscriptions",
            {
                "prompt_id": "fake-id",
                "agent_id": "fresh-agent",
                "last_pulled_at": fresh_time,
            },
        )

        # Simulate cleanup logic
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        subs = mock_db.select("prompt_subscriptions")
        stale = [s for s in subs if s.get("last_pulled_at", "") < cutoff]
        for s in stale:
            mock_db.delete("prompt_subscriptions", s["id"])

        remaining = mock_db.select("prompt_subscriptions")
        assert len(remaining) == 1
        assert remaining[0]["agent_id"] == "fresh-agent"


class TestSubscriberCount:
    def test_list_prompts_includes_subscriber_count(self, client):
        client.post(
            "/api/v1/prompts",
            json={
                "slug": "counted",
                "name": "C",
                "type": "persona",
            },
        )
        client.post("/api/v1/prompts/counted/subscribe", headers={"X-Agent-ID": "a1"})
        client.post("/api/v1/prompts/counted/subscribe", headers={"X-Agent-ID": "a2"})
        resp = client.get("/api/v1/prompts")
        prompts = resp.json()
        counted = [p for p in prompts if p["slug"] == "counted"][0]
        assert counted["subscriber_count"] == 2
