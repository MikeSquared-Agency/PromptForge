"""Tests for smart resolution."""

import pytest

from prompt_forge.core.registry import PromptRegistry
from prompt_forge.core.resolver import PromptResolver
from prompt_forge.core.vcs import VersionControl


class TestPromptResolver:
    def _setup(self, mock_db):
        registry = PromptRegistry(mock_db)
        vcs = VersionControl(mock_db)
        resolver = PromptResolver(mock_db)
        prompt = registry.create_prompt(slug="test", name="Test", type="persona")
        vcs.commit(prompt["id"], {"v": 1}, "v1", "author")
        vcs.commit(prompt["id"], {"v": 2}, "v2", "author")
        vcs.commit(prompt["id"], {"v": 3}, "v3", "author")
        return resolver

    def test_resolve_latest(self, mock_db):
        resolver = self._setup(mock_db)
        result = resolver.resolve("test")
        assert result["version"] == 3

    def test_resolve_pinned(self, mock_db):
        resolver = self._setup(mock_db)
        result = resolver.resolve("test", version=2, strategy="pinned")
        assert result["version"] == 2
        assert result["content"] == {"v": 2}

    def test_resolve_pinned_no_version_raises(self, mock_db):
        resolver = self._setup(mock_db)
        with pytest.raises(ValueError, match="requires a version"):
            resolver.resolve("test", strategy="pinned")

    def test_resolve_not_found(self, mock_db):
        resolver = PromptResolver(mock_db)
        with pytest.raises(ValueError, match="not found"):
            resolver.resolve("nonexistent")

    def test_resolve_best_performing_fallback(self, mock_db):
        resolver = self._setup(mock_db)
        # Falls back to latest in Phase 1
        result = resolver.resolve("test", strategy="best_performing")
        assert result["version"] == 3
