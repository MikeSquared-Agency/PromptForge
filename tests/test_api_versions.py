"""Tests for version API endpoints."""


class TestVersionAPI:
    def _create_prompt(self, client):
        resp = client.post("/api/v1/prompts", json={
            "slug": "versioned", "name": "V", "type": "persona",
        })
        return resp.json()

    def test_create_version(self, client, sample_content):
        self._create_prompt(client)
        resp = client.post("/api/v1/prompts/versioned/versions", json={
            "content": sample_content, "message": "first", "author": "test",
        })
        assert resp.status_code == 201
        assert resp.json()["version"] == 1

    def test_list_versions(self, client, sample_content):
        self._create_prompt(client)
        client.post("/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"})
        client.post("/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v2"})
        resp = client.get("/api/v1/prompts/versioned/versions")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_regression_guard_warns(self, client, sample_content):
        self._create_prompt(client)
        client.post("/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"})
        # Modify content slightly — remove one key
        modified = {**sample_content}
        del modified["variables"]
        resp = client.post("/api/v1/prompts/versioned/versions", json={
            "content": modified, "message": "v2", "acknowledge_reduction": True,
        })
        assert resp.status_code == 201
        assert resp.json()["warnings"] is not None
        assert any(w["type"] == "keys_removed" for w in resp.json()["warnings"])

    def test_regression_guard_blocks(self, client, sample_content):
        self._create_prompt(client)
        client.post("/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"})
        resp = client.post("/api/v1/prompts/versioned/versions", json={
            "content": {"sections": []}, "message": "v2",
        })
        assert resp.status_code == 409
        assert resp.json()["detail"]["error"] == "content_regression_blocked"

    def test_regression_guard_bypass(self, client, sample_content):
        self._create_prompt(client)
        client.post("/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"})
        resp = client.post("/api/v1/prompts/versioned/versions", json={
            "content": {"sections": []}, "message": "v2", "acknowledge_reduction": True,
        })
        assert resp.status_code == 201

    def test_patch_version(self, client, sample_content):
        self._create_prompt(client)
        client.post("/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"})
        resp = client.patch("/api/v1/prompts/versioned/versions", json={
            "content": {"slack_identity": "U0AE9ME4SNB"}, "message": "add slack",
        })
        assert resp.status_code == 201
        assert resp.json()["version"] == 2
        # Original fields preserved
        assert "sections" in resp.json()["content"]
        assert "variables" in resp.json()["content"]
        # New field added
        assert resp.json()["content"]["slack_identity"] == "U0AE9ME4SNB"

    def test_patch_null_removes_field(self, client, sample_content):
        self._create_prompt(client)
        client.post("/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"})
        resp = client.patch("/api/v1/prompts/versioned/versions", json={
            "content": {"variables": None}, "message": "remove variables",
        })
        assert resp.status_code == 201
        assert "variables" not in resp.json()["content"]
        assert "sections" in resp.json()["content"]

    def test_field_diff(self, client):
        self._create_prompt(client)
        v1_content = {"identity": "I am Kai", "voice": "Warm", "principles": ["Be kind"]}
        v2_content = {"identity": "I am Kai v2", "slack_id": "U123"}
        client.post("/api/v1/prompts/versioned/versions", json={"content": v1_content, "message": "v1"})
        client.post("/api/v1/prompts/versioned/versions", json={
            "content": v2_content, "message": "v2", "acknowledge_reduction": True,
        })
        resp = client.get("/api/v1/prompts/versioned/versions/1/diff/2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["from_version"] == 1
        assert data["to_version"] == 2
        actions = {c["field"]: c["action"] for c in data["changes"]}
        assert actions["voice"] == "removed"
        assert actions["principles"] == "removed"
        assert actions["slack_id"] == "added"
        assert actions["identity"] == "modified"

    def test_restore_version(self, client, sample_content):
        self._create_prompt(client)
        client.post("/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"})
        client.post("/api/v1/prompts/versioned/versions", json={
            "content": {"sections": []}, "message": "v2", "acknowledge_reduction": True,
        })
        resp = client.post("/api/v1/prompts/versioned/versions/restore", json={
            "from_version": 1, "message": "Restore v1",
        })
        assert resp.status_code == 201
        assert resp.json()["version"] == 3
        assert resp.json()["content"] == sample_content

    def test_restore_with_patch(self, client, sample_content):
        self._create_prompt(client)
        client.post("/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"})
        client.post("/api/v1/prompts/versioned/versions", json={
            "content": {"sections": []}, "message": "v2", "acknowledge_reduction": True,
        })
        resp = client.post("/api/v1/prompts/versioned/versions/restore", json={
            "from_version": 1,
            "patch": {"slack_id": "U123"},
            "message": "Restore v1 + slack",
        })
        assert resp.status_code == 201
        assert resp.json()["content"]["slack_id"] == "U123"
        assert resp.json()["content"]["sections"] == sample_content["sections"]

    def test_rollback(self, client, sample_content):
        self._create_prompt(client)
        client.post("/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"})
        client.post("/api/v1/prompts/versioned/versions", json={
            "content": {"sections": []}, "message": "v2", "acknowledge_reduction": True,
        })
        resp = client.post("/api/v1/prompts/versioned/rollback", json={"version": 1})
        assert resp.status_code == 200
        assert resp.json()["version"] == 3
        assert resp.json()["content"] == sample_content
