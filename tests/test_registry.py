"""Tests for the prompt registry."""

import pytest

from prompt_forge.core.registry import PromptRegistry


class TestPromptRegistry:
    def test_create_prompt(self, mock_db):
        registry = PromptRegistry(mock_db)
        prompt = registry.create_prompt(
            slug="test-persona",
            name="Test Persona",
            type="persona",
            description="A test",
            tags=["test"],
        )
        assert prompt["slug"] == "test-persona"
        assert prompt["type"] == "persona"
        assert prompt["archived"] is False

    def test_create_prompt_with_content(self, mock_db, sample_content):
        registry = PromptRegistry(mock_db)
        prompt = registry.create_prompt(
            slug="test-persona",
            name="Test",
            type="persona",
            content=sample_content,
        )
        # Should also create a version
        versions = mock_db.select("prompt_versions", filters={"prompt_id": prompt["id"]})
        assert len(versions) == 1
        assert versions[0]["version"] == 1

    def test_create_duplicate_slug_raises(self, mock_db):
        registry = PromptRegistry(mock_db)
        registry.create_prompt(slug="dupe", name="First", type="persona")
        with pytest.raises(ValueError, match="already exists"):
            registry.create_prompt(slug="dupe", name="Second", type="persona")

    def test_get_prompt(self, mock_db):
        registry = PromptRegistry(mock_db)
        registry.create_prompt(slug="finder", name="Finder", type="skill")
        result = registry.get_prompt("finder")
        assert result is not None
        assert result["slug"] == "finder"

    def test_get_prompt_not_found(self, mock_db):
        registry = PromptRegistry(mock_db)
        assert registry.get_prompt("nonexistent") is None

    def test_list_prompts(self, mock_db):
        registry = PromptRegistry(mock_db)
        registry.create_prompt(slug="a", name="A", type="persona")
        registry.create_prompt(slug="b", name="B", type="skill")
        assert len(registry.list_prompts()) == 2

    def test_list_prompts_filter_type(self, mock_db):
        registry = PromptRegistry(mock_db)
        registry.create_prompt(slug="a", name="A", type="persona")
        registry.create_prompt(slug="b", name="B", type="skill")
        results = registry.list_prompts(type="persona")
        assert len(results) == 1
        assert results[0]["slug"] == "a"

    def test_list_prompts_filter_tag(self, mock_db):
        registry = PromptRegistry(mock_db)
        registry.create_prompt(slug="a", name="A", type="persona", tags=["python"])
        registry.create_prompt(slug="b", name="B", type="persona", tags=["rust"])
        results = registry.list_prompts(tag="python")
        assert len(results) == 1

    def test_list_prompts_search(self, mock_db):
        registry = PromptRegistry(mock_db)
        registry.create_prompt(slug="code-reviewer", name="Code Reviewer", type="persona")
        registry.create_prompt(slug="writer", name="Technical Writer", type="persona")
        results = registry.list_prompts(search="code")
        assert len(results) == 1

    def test_update_prompt(self, mock_db):
        registry = PromptRegistry(mock_db)
        registry.create_prompt(slug="updater", name="Old", type="persona")
        updated = registry.update_prompt("updater", name="New")
        assert updated["name"] == "New"

    def test_archive_prompt(self, mock_db):
        registry = PromptRegistry(mock_db)
        registry.create_prompt(slug="archivable", name="Gone", type="persona")
        assert registry.archive_prompt("archivable") is True
        # Should not appear in default listing
        results = registry.list_prompts()
        assert len(results) == 0

    def test_archive_nonexistent(self, mock_db):
        registry = PromptRegistry(mock_db)
        assert registry.archive_prompt("nope") is False
