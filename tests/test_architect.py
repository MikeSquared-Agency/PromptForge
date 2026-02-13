"""Tests for PromptArchitect agent."""

import pytest

from prompt_forge.architect.agent import PromptArchitect
from prompt_forge.core.composer import CompositionEngine
from prompt_forge.core.registry import PromptRegistry
from prompt_forge.core.resolver import PromptResolver
from prompt_forge.core.vcs import VersionControl


class TestPromptArchitect:
    def _setup(self, mock_db, sample_content):
        registry = PromptRegistry(mock_db)
        vcs = VersionControl(mock_db)
        resolver = PromptResolver(mock_db)
        composer = CompositionEngine(resolver, registry)
        architect = PromptArchitect(registry, vcs, composer)
        return architect, registry, vcs

    @pytest.mark.asyncio
    async def test_design_creates_prompt(self, mock_db, sample_content):
        architect, registry, vcs = self._setup(mock_db, sample_content)
        # LLM will fail (no gateway), should fallback to template
        result = await architect.design("A Python code reviewer that checks for security issues")
        assert result["status"] in ("created", "draft")
        assert "content" in result

    @pytest.mark.asyncio
    async def test_design_fallback_content(self, mock_db, sample_content):
        architect, registry, vcs = self._setup(mock_db, sample_content)
        result = await architect.design("Test prompt")
        # Should have sections in content
        assert "sections" in result["content"]
        assert any(s["id"] == "identity" for s in result["content"]["sections"])

    @pytest.mark.asyncio
    async def test_refine_commits_new_version(self, mock_db, sample_content):
        architect, registry, vcs = self._setup(mock_db, sample_content)
        # Create a prompt to refine
        registry.create_prompt(
            slug="refine-test",
            name="Refine Test",
            type="persona",
            content=sample_content,
        )
        result = await architect.refine(
            "refine-test", "Be more specific about Python 3.12 features"
        )
        assert result["status"] == "committed"
        assert result["version"]["version"] == 2

    @pytest.mark.asyncio
    async def test_refine_not_found(self, mock_db, sample_content):
        architect, registry, vcs = self._setup(mock_db, sample_content)
        with pytest.raises(ValueError, match="not found"):
            await architect.refine("nonexistent", "feedback")

    @pytest.mark.asyncio
    async def test_evaluate_returns_report(self, mock_db, sample_content):
        architect, registry, vcs = self._setup(mock_db, sample_content)
        registry.create_prompt(
            slug="eval-test",
            name="Eval Test",
            type="persona",
            content=sample_content,
        )
        report = await architect.evaluate("eval-test")
        assert report.slug == "eval-test"
        assert 0 <= report.structure_score <= 1
        assert 0 <= report.coverage_score <= 1
        assert report.injection_risk in ("low", "medium", "high", "critical")

    @pytest.mark.asyncio
    async def test_evaluate_missing_sections(self, mock_db):
        registry = PromptRegistry(mock_db)
        vcs = VersionControl(mock_db)
        resolver = PromptResolver(mock_db)
        composer = CompositionEngine(resolver, registry)
        architect = PromptArchitect(registry, vcs, composer)

        minimal_content = {
            "sections": [
                {"id": "identity", "label": "Identity", "content": "You are a test agent."}
            ],
            "variables": {},
            "metadata": {},
        }
        registry.create_prompt(
            slug="minimal-test", name="Minimal", type="persona", content=minimal_content
        )
        report = await architect.evaluate("minimal-test")
        assert report.structure_score < 1.0  # Missing sections
        assert any("Missing sections" in s for s in report.suggestions)

    @pytest.mark.asyncio
    async def test_evaluate_not_found(self, mock_db, sample_content):
        architect, registry, vcs = self._setup(mock_db, sample_content)
        with pytest.raises(ValueError, match="not found"):
            await architect.evaluate("nonexistent")
