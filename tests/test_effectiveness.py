"""Tests for prompt effectiveness tracking endpoints."""

from uuid import uuid4


class TestEffectivenessCreate:
    def test_create_effectiveness(self, client, mock_db):
        resp = client.post(
            "/api/v1/effectiveness",
            json={
                "session_uuid": "sess-001",
                "agent_id": "developer",
                "model_id": "claude-sonnet-4-5-20250929",
                "model_tier": "standard",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["session_uuid"] == "sess-001"
        assert data["agent_id"] == "developer"
        assert data["model_id"] == "claude-sonnet-4-5-20250929"
        assert data["correction_count"] == 0
        assert data["outcome"] == "unknown"

    def test_create_with_all_fields(self, client, mock_db):
        prompt_id = str(uuid4())
        version_id = str(uuid4())
        resp = client.post(
            "/api/v1/effectiveness",
            json={
                "session_uuid": "sess-002",
                "prompt_id": prompt_id,
                "version_id": version_id,
                "agent_id": "reviewer",
                "model_id": "claude-opus-4-6",
                "model_tier": "premium",
                "briefing_hash": "abc123",
                "mission_id": "mission-1",
                "task_id": "task-1",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["mission_id"] == "mission-1"
        assert data["briefing_hash"] == "abc123"


class TestEffectivenessUpdate:
    def _create(self, client):
        resp = client.post(
            "/api/v1/effectiveness",
            json={
                "session_uuid": "sess-upd",
                "agent_id": "developer",
                "model_id": "claude-sonnet-4-5-20250929",
            },
        )
        assert resp.status_code == 201
        return resp.json()

    def test_update_tokens(self, client, mock_db):
        self._create(client)
        resp = client.patch(
            "/api/v1/effectiveness/sess-upd",
            json={"input_tokens": 5000, "output_tokens": 2000, "total_tokens": 7000},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["input_tokens"] == 5000
        assert data["total_tokens"] == 7000

    def test_update_outcome(self, client, mock_db):
        self._create(client)
        resp = client.patch(
            "/api/v1/effectiveness/sess-upd",
            json={"outcome": "success", "outcome_score": 0.85, "cost_usd": 0.05},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["outcome"] == "success"
        assert data["outcome_score"] == 0.85

    def test_update_not_found(self, client, mock_db):
        resp = client.patch(
            "/api/v1/effectiveness/nonexistent",
            json={"outcome": "success"},
        )
        assert resp.status_code == 404


class TestEffectivenessSummary:
    def _seed(self, mock_db):
        for i in range(5):
            mock_db.insert(
                "prompt_effectiveness",
                {
                    "session_uuid": f"sess-{i}",
                    "agent_id": "developer" if i < 3 else "reviewer",
                    "model_id": "claude-sonnet-4-5-20250929",
                    "model_tier": "standard",
                    "total_tokens": 5000 + i * 1000,
                    "cost_usd": 0.03 + i * 0.01,
                    "outcome_score": 0.7 + i * 0.05,
                    "effectiveness": (0.7 + i * 0.05) / (0.03 + i * 0.01),
                    "correction_count": i % 2,
                    "created_at": "2026-02-15T00:00:00Z",
                },
            )

    def test_summary_by_agent(self, client, mock_db):
        self._seed(mock_db)
        resp = client.get("/api/v1/effectiveness/summary?group_by=agent_id")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        agents = {d["group_value"] for d in data}
        assert "developer" in agents
        assert "reviewer" in agents

    def test_summary_by_model_tier(self, client, mock_db):
        self._seed(mock_db)
        resp = client.get("/api/v1/effectiveness/summary?group_by=model_tier")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["group_key"] == "model_tier"


class TestModelTierEffectiveness:
    def _seed_tiers(self, mock_db):
        for tier, count in [("economy", 5), ("standard", 10), ("premium", 3)]:
            for i in range(count):
                mock_db.insert(
                    "prompt_effectiveness",
                    {
                        "session_uuid": f"sess-{tier}-{i}",
                        "agent_id": "developer",
                        "model_id": f"model-{tier}",
                        "model_tier": tier,
                        "correction_count": 1 if tier == "economy" and i < 3 else 0,
                        "outcome_score": 0.7 if tier == "economy" else 0.9,
                        "effectiveness": 10.0 if tier == "economy" else 15.0,
                        "created_at": "2026-02-15T00:00:00Z",
                    },
                )

    def test_model_tiers(self, client, mock_db):
        self._seed_tiers(mock_db)
        resp = client.get("/api/v1/effectiveness/model-tiers")
        assert resp.status_code == 200
        data = resp.json()
        assert "economy" in data
        assert "standard" in data
        assert "premium" in data
        assert data["economy"]["session_count"] == 5
        assert data["standard"]["session_count"] == 10


class TestMissionCostBreakdown:
    def _seed_mission(self, mock_db):
        for i in range(4):
            mock_db.insert(
                "prompt_effectiveness",
                {
                    "session_uuid": f"sess-m-{i}",
                    "agent_id": "developer",
                    "model_id": "claude-sonnet-4-5-20250929",
                    "mission_id": "mission-1",
                    "task_id": f"task-{i % 2}",
                    "total_tokens": 5000,
                    "cost_usd": 0.05,
                    "outcome_score": 0.8,
                    "correction_count": 0,
                    "created_at": "2026-02-15T00:00:00Z",
                },
            )

    def test_mission_breakdown(self, client, mock_db):
        self._seed_mission(mock_db)
        resp = client.get("/api/v1/effectiveness/mission/mission-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mission_id"] == "mission-1"
        assert data["total_cost_usd"] == 0.20
        assert data["total_tokens"] == 20000
        assert data["session_count"] == 4
        assert len(data["stages"]) == 2

    def test_mission_not_found(self, client, mock_db):
        resp = client.get("/api/v1/effectiveness/mission/nonexistent")
        assert resp.status_code == 404


class TestDiscoveryAccuracy:
    def _seed_discovery(self, mock_db):
        for i, score in enumerate([0.5, 0.6, 0.7, 0.85]):
            mock_db.insert(
                "prompt_effectiveness",
                {
                    "session_uuid": f"sess-d-{i}",
                    "agent_id": "developer",
                    "model_id": "claude-sonnet-4-5-20250929",
                    "mission_id": "mission-da",
                    "outcome_score": score,
                    "created_at": f"2026-02-1{i + 2}T00:00:00Z",
                },
            )

    def test_discovery_accuracy(self, client, mock_db):
        self._seed_discovery(mock_db)
        resp = client.get("/api/v1/effectiveness/discovery-accuracy")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["mission_id"] == "mission-da"
        assert data[0]["initial_score"] == 0.5
        assert data[0]["final_score"] == 0.85
        assert data[0]["discovery_accuracy"] is not None
