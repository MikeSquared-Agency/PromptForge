"""Tests for version control system."""

import pytest

from prompt_forge.core.registry import PromptRegistry
from prompt_forge.core.vcs import VersionControl, merge_content, regression_check


class TestVersionControl:
    def _create_prompt(self, mock_db):
        registry = PromptRegistry(mock_db)
        return registry.create_prompt(slug="test", name="Test", type="persona")

    def test_commit(self, mock_db, sample_content):
        prompt = self._create_prompt(mock_db)
        vcs = VersionControl(mock_db)
        version = vcs.commit(prompt["id"], sample_content, "Initial", "author")
        assert version["version"] == 1
        assert version["branch"] == "main"
        assert version["content"] == sample_content

    def test_commit_increments_version(self, mock_db, sample_content):
        prompt = self._create_prompt(mock_db)
        vcs = VersionControl(mock_db)
        vcs.commit(prompt["id"], sample_content, "v1", "author")
        v2 = vcs.commit(prompt["id"], sample_content, "v2", "author")
        assert v2["version"] == 2
        assert v2["parent_version_id"] is not None

    def test_history(self, mock_db, sample_content):
        prompt = self._create_prompt(mock_db)
        vcs = VersionControl(mock_db)
        vcs.commit(prompt["id"], sample_content, "v1", "author")
        vcs.commit(prompt["id"], sample_content, "v2", "author")
        vcs.commit(prompt["id"], sample_content, "v3", "author")
        history = vcs.history(prompt["id"])
        assert len(history) == 3
        assert history[0]["version"] == 3  # Most recent first

    def test_history_limit(self, mock_db, sample_content):
        prompt = self._create_prompt(mock_db)
        vcs = VersionControl(mock_db)
        for i in range(5):
            vcs.commit(prompt["id"], sample_content, f"v{i+1}", "author")
        history = vcs.history(prompt["id"], limit=2)
        assert len(history) == 2

    def test_get_version(self, mock_db, sample_content):
        prompt = self._create_prompt(mock_db)
        vcs = VersionControl(mock_db)
        vcs.commit(prompt["id"], sample_content, "v1", "author")
        vcs.commit(prompt["id"], {"sections": []}, "v2", "author")
        v1 = vcs.get_version(prompt["id"], 1)
        assert v1 is not None
        assert v1["content"] == sample_content

    def test_get_version_not_found(self, mock_db):
        prompt = self._create_prompt(mock_db)
        vcs = VersionControl(mock_db)
        assert vcs.get_version(prompt["id"], 99) is None

    def test_rollback(self, mock_db, sample_content):
        prompt = self._create_prompt(mock_db)
        vcs = VersionControl(mock_db)
        vcs.commit(prompt["id"], sample_content, "v1", "author")
        vcs.commit(prompt["id"], {"sections": []}, "v2", "author")
        rolled = vcs.rollback(prompt["id"], 1, "author")
        assert rolled["version"] == 3
        assert rolled["content"] == sample_content
        assert "Rollback" in rolled["message"]

    def test_rollback_nonexistent(self, mock_db):
        prompt = self._create_prompt(mock_db)
        vcs = VersionControl(mock_db)
        assert vcs.rollback(prompt["id"], 99) is None

    def test_branches(self, mock_db, sample_content):
        prompt = self._create_prompt(mock_db)
        vcs = VersionControl(mock_db)
        vcs.commit(prompt["id"], sample_content, "main v1", "author", "main")
        vcs.commit(prompt["id"], {"sections": []}, "exp v1", "author", "experiment")
        main_history = vcs.history(prompt["id"], branch="main")
        exp_history = vcs.history(prompt["id"], branch="experiment")
        assert len(main_history) == 1
        assert len(exp_history) == 1


class TestMergeContent:
    """Unit tests for merge_content."""

    def test_adds_new_fields(self):
        base = {"identity": "I am Kai", "voice": "Warm"}
        patch = {"slack_id": "U123"}
        result = merge_content(base, patch)
        assert result == {"identity": "I am Kai", "voice": "Warm", "slack_id": "U123"}

    def test_replaces_string_field(self):
        base = {"voice": "Warm", "identity": "Kai"}
        patch = {"voice": "Formal"}
        result = merge_content(base, patch)
        assert result["voice"] == "Formal"
        assert result["identity"] == "Kai"

    def test_replaces_array_atomically(self):
        base = {"principles": ["Be kind", "Be honest"]}
        patch = {"principles": ["Be kind", "Be honest", "Be brave"]}
        result = merge_content(base, patch)
        assert result["principles"] == ["Be kind", "Be honest", "Be brave"]

    def test_preserves_omitted_fields(self):
        base = {"a": 1, "b": 2, "c": 3}
        patch = {"b": 20}
        result = merge_content(base, patch)
        assert result == {"a": 1, "b": 20, "c": 3}

    def test_null_removes_field(self):
        base = {"a": 1, "b": 2, "c": 3}
        patch = {"b": None}
        result = merge_content(base, patch)
        assert result == {"a": 1, "c": 3}

    def test_null_on_missing_field_is_noop(self):
        base = {"a": 1}
        patch = {"nonexistent": None}
        result = merge_content(base, patch)
        assert result == {"a": 1}

    def test_deep_merges_objects(self):
        base = {"meta": {"author": "mike", "version": 1}, "name": "test"}
        patch = {"meta": {"version": 2, "reviewed": True}}
        result = merge_content(base, patch)
        assert result["meta"] == {"author": "mike", "version": 2, "reviewed": True}
        assert result["name"] == "test"

    def test_deep_merge_with_null_inside_object(self):
        base = {"meta": {"a": 1, "b": 2}}
        patch = {"meta": {"b": None}}
        result = merge_content(base, patch)
        assert result["meta"] == {"a": 1}

    def test_replaces_non_object_with_object(self):
        base = {"field": "string_value"}
        patch = {"field": {"nested": True}}
        result = merge_content(base, patch)
        assert result["field"] == {"nested": True}

    def test_replaces_object_with_non_object(self):
        base = {"field": {"nested": True}}
        patch = {"field": "string_value"}
        result = merge_content(base, patch)
        assert result["field"] == "string_value"

    def test_empty_patch_preserves_base(self):
        base = {"a": 1, "b": 2}
        result = merge_content(base, {})
        assert result == base

    def test_does_not_mutate_base(self):
        base = {"a": 1, "b": {"nested": True}}
        patch = {"c": 3}
        merge_content(base, patch)
        assert "c" not in base


class TestRegressionCheck:
    """Unit tests for regression_check."""

    def test_no_regression_on_addition(self):
        parent = {"a": "hello"}
        new = {"a": "hello", "b": "world"}
        result = regression_check(parent, new)
        assert result["warn"] is False
        assert result["block"] is False
        assert result["keys_removed"] == []
        assert result["keys_added"] == ["b"]

    def test_warns_on_key_removal(self):
        parent = {"a": "hello", "b": "world", "c": "foo", "d": "bar"}
        new = {"a": "hello", "b": "world", "c": "foo"}
        result = regression_check(parent, new)
        assert result["warn"] is True
        assert result["keys_removed"] == ["d"]

    def test_warns_on_content_reduction_over_20_pct(self):
        parent = {"a": "x" * 100, "b": "y" * 100}
        new = {"a": "x" * 100, "b": "y" * 10}
        result = regression_check(parent, new)
        assert result["content_reduction_pct"] > 20
        assert result["warn"] is True

    def test_blocks_on_over_50_pct_content_reduction(self):
        parent = {"a": "x" * 200, "b": "y" * 200}
        new = {"a": "x" * 20}
        result = regression_check(parent, new)
        assert result["content_reduction_pct"] > 50
        assert result["block"] is True

    def test_blocks_on_over_50_pct_keys_removed(self):
        parent = {"a": "1", "b": "2", "c": "3", "d": "4"}
        new = {"a": "1"}
        result = regression_check(parent, new)
        assert result["block"] is True
        assert len(result["keys_removed"]) == 3

    def test_no_block_on_moderate_change(self):
        parent = {"a": "hello", "b": "world", "c": "foo", "d": "bar"}
        new = {"a": "hello", "b": "world", "c": "foo", "e": "baz"}
        result = regression_check(parent, new)
        assert result["block"] is False

    def test_detects_emptied_fields(self):
        parent = {"a": "hello", "b": ["item1", "item2"]}
        new = {"a": "", "b": []}
        result = regression_check(parent, new)
        assert sorted(result["fields_emptied"]) == ["a", "b"]

    def test_warnings_list_populated(self):
        parent = {"a": "x" * 100, "b": "y" * 100, "c": "z" * 100}
        new = {"a": "x"}
        result = regression_check(parent, new)
        types = {w["type"] for w in result["warnings"]}
        assert "keys_removed" in types
        assert "content_reduction" in types

    def test_no_warnings_on_clean_update(self):
        parent = {"a": "hello"}
        new = {"a": "hello world"}
        result = regression_check(parent, new)
        assert result["warnings"] == []
        assert result["warn"] is False

    def test_empty_parent_no_crash(self):
        result = regression_check({}, {"a": "new"})
        assert result["block"] is False
        assert result["content_reduction_pct"] == 0.0
