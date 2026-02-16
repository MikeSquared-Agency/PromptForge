"""Tests for prompt verbosity analyser (Loop 3)."""

import pytest

from prompt_forge.core.analyser import analyse_verbose_prompts


class TestAnalyseVerbosePrompts:
    def _seed(self, mock_db, version_tokens: dict[str, int]):
        """Seed prompt_effectiveness with per-version average tokens."""
        for vid, avg_tokens in version_tokens.items():
            for i in range(5):
                mock_db.insert(
                    "prompt_effectiveness",
                    {
                        "session_uuid": f"sess-{vid}-{i}",
                        "version_id": vid,
                        "prompt_id": "prompt-1",
                        "agent_id": "developer",
                        "model_id": "claude-sonnet-4-5-20250929",
                        "total_tokens": avg_tokens,
                        "outcome_score": 0.8,
                        "created_at": "2026-02-15T00:00:00Z",
                    },
                )

    @pytest.mark.asyncio
    async def test_flags_verbose_version(self, mock_db, monkeypatch):
        monkeypatch.setattr("prompt_forge.core.analyser.get_supabase_client", lambda: mock_db)
        # 3 versions: A=3000, B=4000 (median), C=20000 (>2x median=4000 → ratio 5.0)
        self._seed(mock_db, {"version-a": 3000, "version-b": 4000, "version-c": 20000})
        flagged = await analyse_verbose_prompts()
        assert len(flagged) == 1
        assert flagged[0]["version_id"] == "version-c"
        assert flagged[0]["token_ratio"] > 2.0

    @pytest.mark.asyncio
    async def test_no_flags_when_similar(self, mock_db, monkeypatch):
        monkeypatch.setattr("prompt_forge.core.analyser.get_supabase_client", lambda: mock_db)
        self._seed(mock_db, {"version-a": 5000, "version-b": 6000, "version-c": 5500})
        flagged = await analyse_verbose_prompts()
        assert len(flagged) == 0

    @pytest.mark.asyncio
    async def test_empty_data(self, mock_db, monkeypatch):
        monkeypatch.setattr("prompt_forge.core.analyser.get_supabase_client", lambda: mock_db)
        flagged = await analyse_verbose_prompts()
        assert flagged == []

    @pytest.mark.asyncio
    async def test_single_version_no_flag(self, mock_db, monkeypatch):
        monkeypatch.setattr("prompt_forge.core.analyser.get_supabase_client", lambda: mock_db)
        self._seed(mock_db, {"version-a": 50000})
        flagged = await analyse_verbose_prompts()
        assert flagged == []
