"""Tests for structural diffing engine."""

from prompt_forge.core.differ import StructuralDiffer


class TestStructuralDiffer:
    def setup_method(self):
        self.differ = StructuralDiffer()

    def test_no_changes(self):
        content = {"sections": [{"id": "a", "content": "hello"}]}
        result = self.differ.diff(content, content)
        assert result["summary"] == "No changes"
        assert len(result["changes"]) == 0

    def test_added_section(self):
        old = {"sections": [{"id": "a", "content": "hello"}]}
        new = {"sections": [{"id": "a", "content": "hello"}, {"id": "b", "content": "world"}]}
        result = self.differ.diff(old, new)
        assert any(c["type"] == "added" and c["section_id"] == "b" for c in result["changes"])

    def test_removed_section(self):
        old = {"sections": [{"id": "a", "content": "hello"}, {"id": "b", "content": "world"}]}
        new = {"sections": [{"id": "a", "content": "hello"}]}
        result = self.differ.diff(old, new)
        assert any(c["type"] == "removed" and c["section_id"] == "b" for c in result["changes"])

    def test_modified_section(self):
        old = {"sections": [{"id": "a", "content": "hello world"}]}
        new = {"sections": [{"id": "a", "content": "hello there"}]}
        result = self.differ.diff(old, new)
        changes = [c for c in result["changes"] if c["section_id"] == "a"]
        assert len(changes) == 1
        assert changes[0]["type"] == "modified"
        assert 0 < changes[0]["similarity"] < 1

    def test_variable_changes(self):
        old = {"sections": [], "variables": {"a": "1"}}
        new = {"sections": [], "variables": {"a": "2"}}
        result = self.differ.diff(old, new)
        assert any(c["section_id"] == "_variables" for c in result["changes"])

    def test_metadata_changes(self):
        old = {"sections": [], "metadata": {"tokens": 100}}
        new = {"sections": [], "metadata": {"tokens": 200}}
        result = self.differ.diff(old, new)
        assert any(c["section_id"] == "_metadata" for c in result["changes"])

    def test_summary_format(self):
        old = {"sections": [{"id": "a", "content": "x"}]}
        new = {"sections": [{"id": "a", "content": "y"}, {"id": "b", "content": "z"}]}
        result = self.differ.diff(old, new)
        assert "added" in result["summary"]
        assert "modified" in result["summary"]

    def test_human_readable(self):
        old = {"sections": [{"id": "a", "content": "old text"}]}
        new = {"sections": [{"id": "a", "content": "new text"}, {"id": "b", "content": "added"}]}
        result = self.differ.diff(old, new)
        text = self.differ.human_readable(result)
        assert "~" in text  # modified marker
        assert "+" in text  # added marker
