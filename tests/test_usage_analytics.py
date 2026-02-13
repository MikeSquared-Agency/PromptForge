"""Tests for usage analytics endpoints."""

from prompt_forge.core.registry import PromptRegistry
from prompt_forge.core.vcs import VersionControl


class TestUsageAnalytics:
    def _seed(self, client, mock_db):
        """Create a prompt and seed usage data via mock_db directly."""
        registry = PromptRegistry(mock_db)
        vcs = VersionControl(mock_db)
        prompt = registry.create_prompt(
            slug="analytics-test", name="Analytics Test", type="persona"
        )
        version = vcs.commit(
            str(prompt["id"]), {"sections": [], "variables": {}, "metadata": {}}, "v1", "author"
        )

        for i in range(5):
            mock_db.insert(
                "prompt_usage_log",
                {
                    "prompt_id": str(prompt["id"]),
                    "version_id": version["id"],
                    "agent_id": f"agent-{i}",
                    "outcome": "success" if i < 3 else "failure",
                    "latency_ms": 100 + i * 50,
                    "composition_manifest": None,
                    "feedback": None,
                    "resolved_at": "2026-02-12T00:00:00Z",
                },
            )

        return str(prompt["id"]), version["id"]

    def test_stats_endpoint(self, client, mock_db):
        self._seed(client, mock_db)
        resp = client.get("/api/v1/usage/stats/analytics-test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_uses"] == 5
        assert data["success_rate"] == 0.6

    def test_all_stats(self, client, mock_db):
        self._seed(client, mock_db)
        resp = client.get("/api/v1/usage/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["total_uses"] == 5

    def test_top_prompts(self, client, mock_db):
        self._seed(client, mock_db)
        resp = client.get("/api/v1/usage/top")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["usage_count"] == 5
        assert data[0]["slug"] == "analytics-test"

    def test_version_performance(self, client, mock_db):
        self._seed(client, mock_db)
        resp = client.get("/api/v1/usage/performance?slug=analytics-test")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["total_uses"] == 5
        assert data[0]["success_rate"] == 0.6

    def test_performance_not_found(self, client, mock_db):
        resp = client.get("/api/v1/usage/performance?slug=nonexistent")
        assert resp.status_code == 404
