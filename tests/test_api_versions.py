"""Tests for version API endpoints."""

import json


class TestVersionAPI:
    def _create_prompt(self, client):
        resp = client.post(
            "/api/v1/prompts",
            json={
                "slug": "versioned",
                "name": "V",
                "type": "persona",
            },
        )
        return resp.json()

    def test_create_version(self, client, sample_content):
        self._create_prompt(client)
        resp = client.post(
            "/api/v1/prompts/versioned/versions",
            json={
                "content": sample_content,
                "message": "first",
                "author": "test",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["version"] == 1

    def test_list_versions(self, client, sample_content):
        self._create_prompt(client)
        client.post(
            "/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"}
        )
        client.post(
            "/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v2"}
        )
        resp = client.get("/api/v1/prompts/versioned/versions")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_regression_guard_warns(self, client, sample_content):
        self._create_prompt(client)
        client.post(
            "/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"}
        )
        # Modify content slightly — remove one key
        modified = {**sample_content}
        del modified["variables"]
        resp = client.post(
            "/api/v1/prompts/versioned/versions",
            json={
                "content": modified,
                "message": "v2",
                "acknowledge_reduction": True,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["warnings"] is not None
        assert any(w["type"] == "keys_removed" for w in resp.json()["warnings"])

    def test_regression_guard_blocks(self, client, sample_content):
        self._create_prompt(client)
        client.post(
            "/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"}
        )
        resp = client.post(
            "/api/v1/prompts/versioned/versions",
            json={
                "content": {"sections": []},
                "message": "v2",
            },
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["error"] == "content_regression_blocked"

    def test_regression_guard_bypass(self, client, sample_content):
        self._create_prompt(client)
        client.post(
            "/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"}
        )
        resp = client.post(
            "/api/v1/prompts/versioned/versions",
            json={
                "content": {"sections": []},
                "message": "v2",
                "acknowledge_reduction": True,
            },
        )
        assert resp.status_code == 201

    def test_patch_version(self, client, sample_content):
        self._create_prompt(client)
        client.post(
            "/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"}
        )
        resp = client.patch(
            "/api/v1/prompts/versioned/versions",
            json={
                "content": {"slack_identity": "U0AE9ME4SNB"},
                "message": "add slack",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["version"] == 2
        # Original fields preserved
        assert "sections" in resp.json()["content"]
        assert "variables" in resp.json()["content"]
        # New field added
        assert resp.json()["content"]["slack_identity"] == "U0AE9ME4SNB"

    def test_patch_null_removes_field(self, client, sample_content):
        self._create_prompt(client)
        client.post(
            "/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"}
        )
        resp = client.patch(
            "/api/v1/prompts/versioned/versions",
            json={
                "content": {"variables": None},
                "message": "remove variables",
            },
        )
        assert resp.status_code == 201
        assert "variables" not in resp.json()["content"]
        assert "sections" in resp.json()["content"]

    def test_field_diff(self, client):
        self._create_prompt(client)
        v1_content = {"identity": "I am Kai", "voice": "Warm", "principles": ["Be kind"]}
        v2_content = {"identity": "I am Kai v2", "slack_id": "U123"}
        client.post(
            "/api/v1/prompts/versioned/versions", json={"content": v1_content, "message": "v1"}
        )
        client.post(
            "/api/v1/prompts/versioned/versions",
            json={
                "content": v2_content,
                "message": "v2",
                "acknowledge_reduction": True,
            },
        )
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
        client.post(
            "/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"}
        )
        client.post(
            "/api/v1/prompts/versioned/versions",
            json={
                "content": {"sections": []},
                "message": "v2",
                "acknowledge_reduction": True,
            },
        )
        resp = client.post(
            "/api/v1/prompts/versioned/versions/restore",
            json={
                "from_version": 1,
                "message": "Restore v1",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["version"] == 3
        assert resp.json()["content"] == sample_content

    def test_restore_with_patch(self, client, sample_content):
        self._create_prompt(client)
        client.post(
            "/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"}
        )
        client.post(
            "/api/v1/prompts/versioned/versions",
            json={
                "content": {"sections": []},
                "message": "v2",
                "acknowledge_reduction": True,
            },
        )
        resp = client.post(
            "/api/v1/prompts/versioned/versions/restore",
            json={
                "from_version": 1,
                "patch": {"slack_id": "U123"},
                "message": "Restore v1 + slack",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["content"]["slack_id"] == "U123"
        assert resp.json()["content"]["sections"] == sample_content["sections"]

    def test_rollback(self, client, sample_content):
        self._create_prompt(client)
        client.post(
            "/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"}
        )
        client.post(
            "/api/v1/prompts/versioned/versions",
            json={
                "content": {"sections": []},
                "message": "v2",
                "acknowledge_reduction": True,
            },
        )
        resp = client.post("/api/v1/prompts/versioned/rollback", json={"version": 1})
        assert resp.status_code == 200
        assert resp.json()["version"] == 3
        assert resp.json()["content"] == sample_content

    def test_get_latest_version(self, client, sample_content):
        """Bug 2: GET /versions/latest returns the most recent version."""
        self._create_prompt(client)
        client.post(
            "/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"}
        )
        client.post(
            "/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v2"}
        )
        resp = client.get("/api/v1/prompts/versioned/versions/latest")
        assert resp.status_code == 200
        assert resp.json()["version"] == 2

    def test_get_latest_version_no_versions_404(self, client):
        """Bug 2: /versions/latest returns 404 if no versions exist."""
        self._create_prompt(client)
        resp = client.get("/api/v1/prompts/versioned/versions/latest")
        assert resp.status_code == 404

    def test_get_latest_does_not_conflict_with_version_int(self, client, sample_content):
        """Bug 2: /versions/latest must not be matched by /versions/{version:int}."""
        self._create_prompt(client)
        client.post(
            "/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"}
        )
        # /versions/1 should still work
        resp_int = client.get("/api/v1/prompts/versioned/versions/1")
        assert resp_int.status_code == 200
        assert resp_int.json()["version"] == 1
        # /versions/latest should work too
        resp_latest = client.get("/api/v1/prompts/versioned/versions/latest")
        assert resp_latest.status_code == 200
        assert resp_latest.json()["version"] == 1

    def test_content_with_control_chars_produces_valid_json(self, client):
        """Bug 1: Content with newlines/tabs must produce valid JSON."""
        self._create_prompt(client)
        content = {
            "voice": "Warm and empathetic.\nUses metaphors.\tAsks probing questions.",
            "identity": "You are Kai.\r\nA helpful assistant.",
        }
        client.post(
            "/api/v1/prompts/versioned/versions", json={"content": content, "message": "v1"}
        )
        resp = client.get("/api/v1/prompts/versioned/versions/latest")
        assert resp.status_code == 200
        # The raw response body must be valid JSON (jq-compatible)
        raw_body = resp.content.decode("utf-8")
        parsed = json.loads(raw_body)  # Would raise if invalid control chars
        assert parsed["content"]["voice"] == content["voice"]
        assert parsed["content"]["identity"] == content["identity"]

    def test_list_versions_valid_json_with_control_chars(self, client):
        """Bug 1: List endpoint also produces valid JSON with control chars."""
        self._create_prompt(client)
        content = {"voice": "Line 1\nLine 2\nLine 3"}
        client.post(
            "/api/v1/prompts/versioned/versions", json={"content": content, "message": "v1"}
        )
        resp = client.get("/api/v1/prompts/versioned/versions")
        assert resp.status_code == 200
        raw_body = resp.content.decode("utf-8")
        parsed = json.loads(raw_body)
        assert parsed[0]["content"]["voice"] == "Line 1\nLine 2\nLine 3"
