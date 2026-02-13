"""Tests for best_performing resolver strategy."""

from prompt_forge.core.registry import PromptRegistry
from prompt_forge.core.resolver import PromptResolver
from prompt_forge.core.vcs import VersionControl


class TestBestPerforming:
    def _setup(self, mock_db):
        registry = PromptRegistry(mock_db)
        vcs = VersionControl(mock_db)
        resolver = PromptResolver(mock_db)
        prompt = registry.create_prompt(slug="perf-test", name="Perf Test", type="persona")
        v1 = vcs.commit(str(prompt["id"]), {"v": 1}, "v1", "author")
        v2 = vcs.commit(str(prompt["id"]), {"v": 2}, "v2", "author")
        v3 = vcs.commit(str(prompt["id"]), {"v": 3}, "v3", "author")
        return resolver, prompt, v1, v2, v3

    def test_falls_back_to_latest_no_usage(self, mock_db):
        resolver, prompt, v1, v2, v3 = self._setup(mock_db)
        result = resolver.resolve("perf-test", strategy="best_performing")
        assert result["version"] == 3

    def test_falls_back_with_insufficient_data(self, mock_db):
        resolver, prompt, v1, v2, v3 = self._setup(mock_db)
        # Only 2 uses (below threshold of 3)
        for _ in range(2):
            mock_db.insert(
                "prompt_usage_log",
                {
                    "prompt_id": str(prompt["id"]),
                    "version_id": v1["id"],
                    "agent_id": "test",
                    "outcome": "success",
                },
            )
        result = resolver.resolve("perf-test", strategy="best_performing")
        assert result["version"] == 3  # fallback to latest

    def test_picks_best_version(self, mock_db):
        resolver, prompt, v1, v2, v3 = self._setup(mock_db)
        pid = str(prompt["id"])

        # v1: 2/5 success (40%)
        for i in range(5):
            mock_db.insert(
                "prompt_usage_log",
                {
                    "prompt_id": pid,
                    "version_id": v1["id"],
                    "agent_id": "test",
                    "outcome": "success" if i < 2 else "failure",
                },
            )

        # v2: 4/5 success (80%) — best
        for i in range(5):
            mock_db.insert(
                "prompt_usage_log",
                {
                    "prompt_id": pid,
                    "version_id": v2["id"],
                    "agent_id": "test",
                    "outcome": "success" if i < 4 else "failure",
                },
            )

        # v3: 3/5 success (60%)
        for i in range(5):
            mock_db.insert(
                "prompt_usage_log",
                {
                    "prompt_id": pid,
                    "version_id": v3["id"],
                    "agent_id": "test",
                    "outcome": "success" if i < 3 else "failure",
                },
            )

        result = resolver.resolve("perf-test", strategy="best_performing")
        assert result["version"] == 2  # v2 has highest success rate
