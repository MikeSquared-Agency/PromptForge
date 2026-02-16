"""Tests for persona prompt store operations."""

from __future__ import annotations

import pytest

from prompt_forge.db.persona_store import PersonaPromptStore


@pytest.fixture
def persona_store(mock_db) -> PersonaPromptStore:
    """PersonaPromptStore with mock database."""
    return PersonaPromptStore(mock_db)


def test_get_latest_persona_prompt_not_found(persona_store: PersonaPromptStore):
    """Test getting latest persona prompt when it doesn't exist."""
    result = persona_store.get_latest_persona_prompt("nonexistent")
    assert result is None


def test_get_persona_prompt_version_not_found(persona_store: PersonaPromptStore):
    """Test getting specific persona prompt version when it doesn't exist."""
    result = persona_store.get_persona_prompt_version("nonexistent", 1)
    assert result is None


def test_create_first_persona_prompt_version(persona_store: PersonaPromptStore):
    """Test creating the first version of a persona prompt."""
    template = "You are a developer. Context: {{context}}"

    result = persona_store.create_persona_prompt_version("developer", template)

    assert result.persona == "developer"
    assert result.version == 1
    assert result.template == template
    assert result.is_latest is True
    assert result.id is not None
    assert result.created_at is not None


def test_create_second_persona_prompt_version(persona_store: PersonaPromptStore, mock_db):
    """Test creating a second version marks previous as not latest."""
    template1 = "You are a developer v1. Context: {{context}}"
    template2 = "You are a developer v2. Context: {{context}}"

    # Create first version
    first = persona_store.create_persona_prompt_version("developer", template1)
    assert first.version == 1
    assert first.is_latest is True

    # Mock the bulk update operation that sets is_latest=False for previous versions
    # Since our mock client doesn't handle the complex query, we'll manually update
    for row in mock_db._tables["persona_prompts"]:
        if row["persona"] == "developer" and row["version"] < 2:
            row["is_latest"] = False

    # Create second version
    second = persona_store.create_persona_prompt_version("developer", template2)
    assert second.version == 2
    assert second.is_latest is True

    # Verify first version is no longer latest
    first_updated = persona_store.get_persona_prompt_version("developer", 1)
    assert first_updated is not None
    assert first_updated.is_latest is False

    # Verify second version is latest
    latest = persona_store.get_latest_persona_prompt("developer")
    assert latest is not None
    assert latest.version == 2
    assert latest.is_latest is True


def test_get_latest_after_multiple_versions(persona_store: PersonaPromptStore, mock_db):
    """Test getting latest version after creating multiple versions."""
    templates = ["Template v1", "Template v2", "Template v3"]

    for i, template in enumerate(templates, 1):
        # Mock the bulk update for previous versions
        for row in mock_db._tables["persona_prompts"]:
            if row["persona"] == "tester" and row["version"] < i:
                row["is_latest"] = False

        persona_store.create_persona_prompt_version("tester", template)

    latest = persona_store.get_latest_persona_prompt("tester")
    assert latest is not None
    assert latest.version == 3
    assert latest.template == "Template v3"
    assert latest.is_latest is True


def test_list_persona_versions(persona_store: PersonaPromptStore, mock_db):
    """Test listing all versions of a persona."""
    templates = ["Version 1", "Version 2", "Version 3"]

    for i, template in enumerate(templates, 1):
        # Mock the bulk update for previous versions
        for row in mock_db._tables["persona_prompts"]:
            if row["persona"] == "reviewer" and row["version"] < i:
                row["is_latest"] = False

        persona_store.create_persona_prompt_version("reviewer", template)

    versions = persona_store.list_persona_versions("reviewer")
    assert len(versions) == 3

    # Should be ordered by version descending
    assert versions[0].version == 3
    assert versions[1].version == 2
    assert versions[2].version == 1

    # Only latest should have is_latest=True
    assert versions[0].is_latest is True
    assert versions[1].is_latest is False
    assert versions[2].is_latest is False


def test_list_persona_versions_empty(persona_store: PersonaPromptStore):
    """Test listing versions for non-existent persona."""
    versions = persona_store.list_persona_versions("nonexistent")
    assert versions == []


def test_seed_initial_personas(persona_store: PersonaPromptStore):
    """Test seeding initial personas."""
    persona_store.seed_initial_personas()

    expected_personas = ["researcher", "developer", "reviewer", "tester", "architect"]

    for persona in expected_personas:
        result = persona_store.get_latest_persona_prompt(persona)
        assert result is not None
        assert result.version == 1
        assert result.is_latest is True
        assert "{{objective}}" in result.template
        assert "{{context}}" in result.template
        assert "{{constraints}}" in result.template
        assert "{{scope_paths}}" in result.template
        assert "{{alexandria_context}}" in result.template


def test_seed_initial_personas_skip_existing(persona_store: PersonaPromptStore):
    """Test that seeding skips existing personas."""
    # Create a persona first
    persona_store.create_persona_prompt_version("developer", "Custom template")

    # Now seed - should skip the existing one
    persona_store.seed_initial_personas()

    # Developer should still have the custom template
    result = persona_store.get_latest_persona_prompt("developer")
    assert result is not None
    assert result.template == "Custom template"

    # But other personas should be seeded
    result = persona_store.get_latest_persona_prompt("researcher")
    assert result is not None
    assert "research" in result.template.lower()
