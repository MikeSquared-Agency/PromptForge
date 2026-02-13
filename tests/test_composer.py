"""Tests for the composition engine."""

from prompt_forge.core.composer import CompositionEngine
from prompt_forge.core.registry import PromptRegistry
from prompt_forge.core.resolver import PromptResolver
from prompt_forge.core.vcs import VersionControl


class TestCompositionEngine:
    def _setup(self, mock_db):
        registry = PromptRegistry(mock_db)
        vcs = VersionControl(mock_db)
        resolver = PromptResolver(mock_db)
        composer = CompositionEngine(resolver)
        return registry, vcs, composer

    def _create_component(self, registry, vcs, slug, type_, text):
        prompt = registry.create_prompt(slug=slug, name=slug, type=type_)
        vcs.commit(
            prompt["id"],
            {"sections": [{"id": "main", "content": text}]},
            "init",
            "test",
        )

    def test_compose_basic(self, mock_db):
        registry, vcs, composer = self._setup(mock_db)
        self._create_component(registry, vcs, "reviewer", "persona", "You are a code reviewer.")
        result = composer.compose(persona_slug="reviewer")
        assert "code reviewer" in result["prompt"]
        assert result["manifest"]["components"][0]["slug"] == "reviewer"

    def test_compose_with_skills(self, mock_db):
        registry, vcs, composer = self._setup(mock_db)
        self._create_component(registry, vcs, "reviewer", "persona", "You are a reviewer.")
        self._create_component(registry, vcs, "python-expert", "skill", "Expert in Python.")
        result = composer.compose(persona_slug="reviewer", skill_slugs=["python-expert"])
        assert "Python" in result["prompt"]
        assert len(result["manifest"]["components"]) == 2

    def test_compose_with_variables(self, mock_db):
        registry, vcs, composer = self._setup(mock_db)
        self._create_component(
            registry, vcs, "reviewer", "persona", "Review {{project_name}} code."
        )
        result = composer.compose(
            persona_slug="reviewer",
            variables={"project_name": "PromptForge"},
        )
        assert "PromptForge" in result["prompt"]
        assert "{{project_name}}" not in result["prompt"]

    def test_compose_unresolved_variables_warning(self, mock_db):
        registry, vcs, composer = self._setup(mock_db)
        self._create_component(registry, vcs, "reviewer", "persona", "Review {{project_name}}.")
        result = composer.compose(persona_slug="reviewer")
        assert any("Unresolved" in w for w in result["warnings"])

    def test_compose_missing_skill_warning(self, mock_db):
        registry, vcs, composer = self._setup(mock_db)
        self._create_component(registry, vcs, "reviewer", "persona", "Reviewer.")
        result = composer.compose(persona_slug="reviewer", skill_slugs=["nonexistent"])
        assert any("Failed to resolve" in w for w in result["warnings"])

    def test_compose_manifest_tokens(self, mock_db):
        registry, vcs, composer = self._setup(mock_db)
        self._create_component(registry, vcs, "reviewer", "persona", "A" * 400)
        result = composer.compose(persona_slug="reviewer")
        assert result["manifest"]["estimated_tokens"] == 100  # 400 chars / 4

    def test_compose_conflict_detection(self, mock_db):
        registry, vcs, composer = self._setup(mock_db)
        self._create_component(registry, vcs, "p", "persona", "Respond in JSON format.")
        self._create_component(registry, vcs, "s", "skill", "Respond in markdown format.")
        result = composer.compose(persona_slug="p", skill_slugs=["s"])
        assert any("Conflicting" in w for w in result["warnings"])
