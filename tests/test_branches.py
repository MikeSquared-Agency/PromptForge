"""Tests for branch management."""

import pytest

from prompt_forge.core.registry import PromptRegistry
from prompt_forge.core.vcs import VersionControl


class TestBranchManagement:
    def _setup(self, mock_db, sample_content):
        registry = PromptRegistry(mock_db)
        vcs = VersionControl(mock_db)
        prompt = registry.create_prompt(
            slug="test-branch", name="Test", type="persona", content=sample_content
        )
        return vcs, prompt

    def test_create_branch(self, mock_db, sample_content):
        vcs, prompt = self._setup(mock_db, sample_content)
        branch = vcs.create_branch(str(prompt["id"]), "experiment")
        assert branch["name"] == "experiment"
        assert branch["status"] == "active"

    def test_create_branch_duplicate_raises(self, mock_db, sample_content):
        vcs, prompt = self._setup(mock_db, sample_content)
        vcs.create_branch(str(prompt["id"]), "experiment")
        with pytest.raises(ValueError, match="already exists"):
            vcs.create_branch(str(prompt["id"]), "experiment")

    def test_create_branch_copies_content(self, mock_db, sample_content):
        vcs, prompt = self._setup(mock_db, sample_content)
        vcs.create_branch(str(prompt["id"]), "experiment")
        history = vcs.history(str(prompt["id"]), branch="experiment")
        assert len(history) == 1
        assert history[0]["content"] == sample_content

    def test_list_branches(self, mock_db, sample_content):
        vcs, prompt = self._setup(mock_db, sample_content)
        vcs.create_branch(str(prompt["id"]), "exp-1")
        vcs.create_branch(str(prompt["id"]), "exp-2")
        branches = vcs.list_branches(str(prompt["id"]))
        assert len(branches) == 2
        names = {b["name"] for b in branches}
        assert names == {"exp-1", "exp-2"}

    def test_merge_theirs(self, mock_db, sample_content):
        vcs, prompt = self._setup(mock_db, sample_content)
        pid = str(prompt["id"])
        vcs.create_branch(pid, "experiment")

        new_content = {
            "sections": [{"id": "identity", "label": "Identity", "content": "New identity"}],
            "variables": {},
            "metadata": {},
        }
        vcs.commit(pid, new_content, "Update on experiment", "author", "experiment")

        merged = vcs.merge_branch(pid, "experiment", "main", strategy="theirs")
        assert merged["content"] == new_content

    def test_merge_ours(self, mock_db, sample_content):
        vcs, prompt = self._setup(mock_db, sample_content)
        pid = str(prompt["id"])
        vcs.create_branch(pid, "experiment")

        vcs.commit(pid, {"sections": []}, "Update experiment", "author", "experiment")

        merged = vcs.merge_branch(pid, "experiment", "main", strategy="ours")
        # Should keep main's content (sample_content)
        assert merged["content"] == sample_content

    def test_merge_section_merge(self, mock_db, sample_content):
        vcs, prompt = self._setup(mock_db, sample_content)
        pid = str(prompt["id"])
        vcs.create_branch(pid, "experiment")

        # Add a new section on experiment
        exp_content = {
            "sections": [
                {"id": "identity", "label": "Identity", "content": "Updated identity"},
                {"id": "new_section", "label": "New", "content": "Brand new"},
            ],
            "variables": {"new_var": "value"},
            "metadata": {},
        }
        vcs.commit(pid, exp_content, "Experiment changes", "author", "experiment")

        merged = vcs.merge_branch(pid, "experiment", "main", strategy="section_merge")
        merged_ids = {s["id"] for s in merged["content"]["sections"]}
        # Should have sections from both
        assert "identity" in merged_ids
        assert "new_section" in merged_ids
        assert "skills" in merged_ids  # from main
        assert merged["content"]["variables"].get("new_var") == "value"

    def test_merge_marks_branch_merged(self, mock_db, sample_content):
        vcs, prompt = self._setup(mock_db, sample_content)
        pid = str(prompt["id"])
        vcs.create_branch(pid, "experiment")
        vcs.merge_branch(pid, "experiment", "main")
        branches = vcs.list_branches(pid)
        exp = [b for b in branches if b["name"] == "experiment"][0]
        assert exp["status"] == "merged"


class TestBranchAPI:
    def test_create_branch_api(self, client):
        # Create a prompt first
        client.post(
            "/api/v1/prompts",
            json={
                "slug": "branch-api-test",
                "name": "Branch API Test",
                "type": "persona",
                "content": {
                    "sections": [{"id": "identity", "label": "Identity", "content": "Test"}],
                    "variables": {},
                    "metadata": {},
                },
            },
        )
        resp = client.post("/api/v1/prompts/branch-api-test/branches", json={"name": "experiment"})
        assert resp.status_code == 201
        assert resp.json()["name"] == "experiment"

    def test_list_branches_api(self, client):
        client.post(
            "/api/v1/prompts",
            json={
                "slug": "branch-list-test",
                "name": "Test",
                "type": "persona",
                "content": {
                    "sections": [{"id": "identity", "label": "Identity", "content": "Test"}],
                    "variables": {},
                    "metadata": {},
                },
            },
        )
        client.post("/api/v1/prompts/branch-list-test/branches", json={"name": "exp-1"})
        client.post("/api/v1/prompts/branch-list-test/branches", json={"name": "exp-2"})
        resp = client.get("/api/v1/prompts/branch-list-test/branches")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_merge_branch_api(self, client):
        client.post(
            "/api/v1/prompts",
            json={
                "slug": "branch-merge-test",
                "name": "Test",
                "type": "persona",
                "content": {
                    "sections": [{"id": "identity", "label": "Identity", "content": "Test"}],
                    "variables": {},
                    "metadata": {},
                },
            },
        )
        client.post("/api/v1/prompts/branch-merge-test/branches", json={"name": "feature"})
        resp = client.post(
            "/api/v1/prompts/branch-merge-test/branches/feature/merge",
            json={"strategy": "theirs"},
        )
        assert resp.status_code == 200

    def test_branch_not_found(self, client):
        resp = client.post("/api/v1/prompts/nonexistent/branches", json={"name": "x"})
        assert resp.status_code == 404


class TestNewBranchEndpoints:
    def test_branch_diff_api(self, client):
        # Create a prompt
        client.post(
            "/api/v1/prompts",
            json={
                "slug": "branch-diff-test",
                "name": "Branch Diff Test",
                "type": "persona",
                "content": {
                    "sections": [
                        {"id": "identity", "label": "Identity", "content": "Original content"}
                    ],
                    "variables": {"var1": "value1"},
                    "metadata": {},
                },
            },
        )

        # Create a branch
        client.post("/api/v1/prompts/branch-diff-test/branches", json={"name": "feature"})

        # Update the branch with new content
        client.post(
            "/api/v1/prompts/branch-diff-test/versions",
            json={
                "content": {
                    "sections": [{"id": "identity", "label": "Identity", "content": "New content"}],
                    "variables": {"var1": "value1", "var2": "value2"},
                    "metadata": {},
                },
                "message": "Update feature branch",
                "branch": "feature",
            },
        )

        # Test the diff endpoint
        resp = client.get("/api/v1/prompts/branch-diff-test/branches/feature/diff")
        assert resp.status_code == 200
        data = resp.json()
        assert data["branch_name"] == "feature"
        assert "diff_summary" in data
        assert "current_content" in data
        assert "proposed_content" in data
        assert data["current_content"]["sections"][0]["content"] == "Original content"
        assert data["proposed_content"]["sections"][0]["content"] == "New content"

    def test_branch_diff_branch_not_found(self, client):
        client.post(
            "/api/v1/prompts",
            json={
                "slug": "diff-404-test",
                "name": "Test",
                "type": "persona",
                "content": {
                    "sections": [{"id": "identity", "label": "Identity", "content": "Test"}],
                    "variables": {},
                    "metadata": {},
                },
            },
        )
        resp = client.get("/api/v1/prompts/diff-404-test/branches/nonexistent/diff")
        assert resp.status_code == 404

    def test_branch_reject_api(self, client):
        # Create a prompt
        client.post(
            "/api/v1/prompts",
            json={
                "slug": "branch-reject-test",
                "name": "Branch Reject Test",
                "type": "persona",
                "content": {
                    "sections": [{"id": "identity", "label": "Identity", "content": "Test"}],
                    "variables": {},
                    "metadata": {},
                },
            },
        )

        # Create a branch
        client.post("/api/v1/prompts/branch-reject-test/branches", json={"name": "unwanted"})

        # Reject the branch
        resp = client.post(
            "/api/v1/prompts/branch-reject-test/branches/unwanted/reject",
            json={"reason": "Not needed anymore"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"

    def test_branch_reject_branch_not_found(self, client):
        client.post(
            "/api/v1/prompts",
            json={
                "slug": "reject-404-test",
                "name": "Test",
                "type": "persona",
                "content": {
                    "sections": [{"id": "identity", "label": "Identity", "content": "Test"}],
                    "variables": {},
                    "metadata": {},
                },
            },
        )
        resp = client.post("/api/v1/prompts/reject-404-test/branches/nonexistent/reject", json={})
        assert resp.status_code == 404
