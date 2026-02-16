"""Tests for autonomy expansion analyser (Loop 4)."""

import pytest

from prompt_forge.core.autonomy import analyse_autonomy_candidates


class TestAnalyseAutonomyCandidates:
    def _seed(self, mock_db, agent_id: str, count: int, interventions: int):
        """Seed prompt_effectiveness with sessions for an agent."""
        for i in range(count):
            mock_db.insert(
                "prompt_effectiveness",
                {
                    "session_uuid": f"sess-{agent_id}-{i}",
                    "agent_id": agent_id,
                    "model_id": "claude-sonnet-4-5-20250929",
                    "human_interventions": 1 if i < interventions else 0,
                    "outcome_score": 0.85,
                    "completed_at": "2026-02-15T12:00:00Z",
                    "created_at": "2026-02-15T00:00:00Z",
                },
            )

    @pytest.mark.asyncio
    async def test_flags_high_alignment(self, mock_db, monkeypatch):
        monkeypatch.setattr("prompt_forge.core.autonomy.get_supabase_client", lambda: mock_db)
        # 20 sessions, 1 with intervention (95% alignment)
        self._seed(mock_db, "developer", 20, 1)
        candidates = await analyse_autonomy_candidates()
        assert len(candidates) == 1
        assert candidates[0]["agent_id"] == "developer"
        assert candidates[0]["alignment_rate"] >= 0.9

    @pytest.mark.asyncio
    async def test_no_flag_low_alignment(self, mock_db, monkeypatch):
        monkeypatch.setattr("prompt_forge.core.autonomy.get_supabase_client", lambda: mock_db)
        # 20 sessions, 5 with intervention (75% alignment)
        self._seed(mock_db, "developer", 20, 5)
        candidates = await analyse_autonomy_candidates()
        assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_no_flag_insufficient_sessions(self, mock_db, monkeypatch):
        monkeypatch.setattr("prompt_forge.core.autonomy.get_supabase_client", lambda: mock_db)
        # Only 5 sessions (below threshold of 10)
        self._seed(mock_db, "developer", 5, 0)
        candidates = await analyse_autonomy_candidates()
        assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_empty_data(self, mock_db, monkeypatch):
        monkeypatch.setattr("prompt_forge.core.autonomy.get_supabase_client", lambda: mock_db)
        candidates = await analyse_autonomy_candidates()
        assert candidates == []

    @pytest.mark.asyncio
    async def test_multiple_agents(self, mock_db, monkeypatch):
        monkeypatch.setattr("prompt_forge.core.autonomy.get_supabase_client", lambda: mock_db)
        # developer: 95% alignment (candidate)
        self._seed(mock_db, "developer", 20, 1)
        # reviewer: 70% alignment (not candidate)
        self._seed(mock_db, "reviewer", 20, 6)
        candidates = await analyse_autonomy_candidates()
        assert len(candidates) == 1
        assert candidates[0]["agent_id"] == "developer"
