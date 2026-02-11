"""Tests for version control system."""

from prompt_forge.core.registry import PromptRegistry
from prompt_forge.core.vcs import VersionControl


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
