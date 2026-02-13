"""Tests for prompt inheritance."""

from __future__ import annotations

import pytest

from prompt_forge.core.composer import CompositionEngine
from prompt_forge.core.registry import PromptRegistry
from prompt_forge.core.resolver import PromptResolver
from prompt_forge.core.vcs import VersionControl
from tests.conftest import MockSupabaseClient


@pytest.fixture
def db():
    return MockSupabaseClient()


@pytest.fixture
def registry(db):
    return PromptRegistry(db)


@pytest.fixture
def vcs(db):
    return VersionControl(db)


@pytest.fixture
def resolver(db):
    return PromptResolver(db)


def _make_content(sections: dict[str, str]) -> dict:
    return {
        "sections": [{"id": k, "label": k.title(), "content": v} for k, v in sections.items()],
        "variables": {},
        "metadata": {},
    }


class TestInheritance:
    def test_child_inherits_parent_sections(self, registry, vcs):
        """Child inherits sections from parent that it doesn't override."""
        registry.create_prompt(
            slug="researcher",
            name="Researcher",
            type="persona",
            content=_make_content(
                {"identity": "You are a researcher.", "skills": "You research things."}
            ),
        )
        registry.create_prompt(
            slug="senior-researcher",
            name="Senior Researcher",
            type="persona",
            parent_slug="researcher",
            content=_make_content({"identity": "You are a senior researcher."}),
        )

        effective = registry.get_effective_content("senior-researcher")
        section_map = {s["id"]: s["content"] for s in effective["sections"]}

        # Child overrides identity
        assert section_map["identity"] == "You are a senior researcher."
        # Child inherits skills from parent
        assert section_map["skills"] == "You research things."

    def test_child_overrides_work(self, registry):
        """Child sections replace parent sections with same id."""
        registry.create_prompt(
            slug="base-agent",
            name="Base Agent",
            type="persona",
            content=_make_content({"identity": "Base identity", "tone": "Formal"}),
        )
        registry.create_prompt(
            slug="casual-agent",
            name="Casual Agent",
            type="persona",
            parent_slug="base-agent",
            content=_make_content({"tone": "Very casual and friendly"}),
        )

        effective = registry.get_effective_content("casual-agent")
        section_map = {s["id"]: s["content"] for s in effective["sections"]}

        assert section_map["identity"] == "Base identity"  # inherited
        assert section_map["tone"] == "Very casual and friendly"  # overridden

    def test_deep_inheritance(self, registry):
        """Grandchild → child → parent chain works."""
        registry.create_prompt(
            slug="base",
            name="Base",
            type="persona",
            content=_make_content({"a": "A from base", "b": "B from base", "c": "C from base"}),
        )
        registry.create_prompt(
            slug="mid",
            name="Mid",
            type="persona",
            parent_slug="base",
            content=_make_content({"b": "B from mid"}),
        )
        registry.create_prompt(
            slug="leaf",
            name="Leaf",
            type="persona",
            parent_slug="mid",
            content=_make_content({"c": "C from leaf"}),
        )

        effective = registry.get_effective_content("leaf")
        section_map = {s["id"]: s["content"] for s in effective["sections"]}

        assert section_map["a"] == "A from base"
        assert section_map["b"] == "B from mid"
        assert section_map["c"] == "C from leaf"

    def test_circular_inheritance_detection(self, registry, db):
        """Circular inheritance raises ValueError."""
        # Create A
        registry.create_prompt(slug="aa", name="A", type="persona")
        # Create B extending A
        registry.create_prompt(slug="bb", name="B", type="persona", parent_slug="aa")
        # Manually set A's parent to B to create cycle
        prompt_a = registry.get_prompt("aa")
        db.update("prompts", prompt_a["id"], {"parent_slug": "bb"})

        with pytest.raises(ValueError, match="Circular inheritance"):
            registry.get_prompt_chain("aa")

    def test_parent_not_found_raises(self, registry):
        """Creating prompt with non-existent parent raises."""
        with pytest.raises(ValueError, match="not found"):
            registry.create_prompt(
                slug="orphan", name="Orphan", type="persona", parent_slug="nonexistent"
            )

    def test_prompt_chain(self, registry):
        """get_prompt_chain returns correct order."""
        registry.create_prompt(slug="grandparent", name="GP", type="persona")
        registry.create_prompt(
            slug="parent-chain", name="P", type="persona", parent_slug="grandparent"
        )
        registry.create_prompt(
            slug="child-chain", name="C", type="persona", parent_slug="parent-chain"
        )

        chain = registry.get_prompt_chain("child-chain")
        assert [p["slug"] for p in chain] == ["child-chain", "parent-chain", "grandparent"]

    def test_composition_with_inherited_prompts(self, registry, resolver):
        """Composition resolves inheritance before assembling."""
        registry.create_prompt(
            slug="base-persona",
            name="Base",
            type="persona",
            content=_make_content({"identity": "Base identity", "skills": "Base skills"}),
        )
        registry.create_prompt(
            slug="extended-persona",
            name="Extended",
            type="persona",
            parent_slug="base-persona",
            content=_make_content({"identity": "Extended identity"}),
        )

        composer = CompositionEngine(resolver, registry)
        result = composer.compose(persona_slug="extended-persona")

        assert "Extended identity" in result["prompt"]
        assert "Base skills" in result["prompt"]
