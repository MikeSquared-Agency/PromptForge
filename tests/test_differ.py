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


class TestFieldDiff:
    """Unit tests for field_diff (top-level key comparison)."""

    def setup_method(self):
        self.differ = StructuralDiffer()

    def test_no_changes(self):
        content = {"a": "hello", "b": "world"}
        result = self.differ.field_diff(content, content, 1, 2)
        assert result["summary"]["added"] == 0
        assert result["summary"]["removed"] == 0
        assert result["summary"]["modified"] == 0
        assert result["summary"]["unchanged"] == 2
        assert result["changes"] == []

    def test_detects_added_fields(self):
        old = {"a": "hello"}
        new = {"a": "hello", "b": "world"}
        result = self.differ.field_diff(old, new, 1, 2)
        assert result["summary"]["added"] == 1
        added = [c for c in result["changes"] if c["action"] == "added"]
        assert len(added) == 1
        assert added[0]["field"] == "b"

    def test_detects_removed_fields(self):
        old = {"a": "hello", "b": "world"}
        new = {"a": "hello"}
        result = self.differ.field_diff(old, new, 1, 2)
        assert result["summary"]["removed"] == 1
        removed = [c for c in result["changes"] if c["action"] == "removed"]
        assert removed[0]["field"] == "b"

    def test_detects_modified_fields(self):
        old = {"a": "hello"}
        new = {"a": "hello world, this is longer now"}
        result = self.differ.field_diff(old, new, 1, 2)
        assert result["summary"]["modified"] == 1
        modified = [c for c in result["changes"] if c["action"] == "modified"]
        assert modified[0]["field"] == "a"
        assert "from_length" in modified[0]
        assert "to_length" in modified[0]
        assert modified[0]["to_length"] > modified[0]["from_length"]

    def test_unchanged_fields_counted(self):
        old = {"a": "same", "b": "also same", "c": "different"}
        new = {"a": "same", "b": "also same", "c": "changed"}
        result = self.differ.field_diff(old, new, 1, 2)
        assert result["summary"]["unchanged"] == 2
        assert result["summary"]["modified"] == 1

    def test_content_change_pct_negative_for_reduction(self):
        old = {"a": "x" * 200}
        new = {"a": "x" * 50}
        result = self.differ.field_diff(old, new, 1, 2)
        assert result["summary"]["content_change_pct"] < 0

    def test_content_change_pct_positive_for_growth(self):
        old = {"a": "x" * 50}
        new = {"a": "x" * 200}
        result = self.differ.field_diff(old, new, 1, 2)
        assert result["summary"]["content_change_pct"] > 0

    def test_version_numbers_in_result(self):
        result = self.differ.field_diff({"a": 1}, {"a": 1}, 3, 7)
        assert result["from_version"] == 3
        assert result["to_version"] == 7

    def test_complex_diff_matches_spec_shape(self):
        """Verify output matches the shape from the spec."""
        old = {
            "identity": "I am Kai" * 20,
            "voice": "Friendly",
            "personality": "Curious",
            "principles": ["Be kind"],
            "constraints": ["No profanity"],
            "capabilities": "Code review",
        }
        new = {
            "identity": "Short",
            "capabilities": "Code review",
            "slack_identity": "U123",
            "slack_rules": "Footer rule",
        }
        result = self.differ.field_diff(old, new, 1, 3)
        actions = {c["field"]: c["action"] for c in result["changes"]}
        assert actions["voice"] == "removed"
        assert actions["personality"] == "removed"
        assert actions["principles"] == "removed"
        assert actions["constraints"] == "removed"
        assert actions["identity"] == "modified"
        assert actions["slack_identity"] == "added"
        assert actions["slack_rules"] == "added"
        assert result["summary"]["added"] == 2
        assert result["summary"]["removed"] == 4
        assert result["summary"]["modified"] == 1
        assert result["summary"]["unchanged"] == 1
        assert result["summary"]["content_change_pct"] < 0
