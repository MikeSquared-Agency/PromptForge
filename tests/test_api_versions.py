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

    def test_rollback(self, client, sample_content):
        self._create_prompt(client)
        client.post("/api/v1/prompts/versioned/versions", json={"content": sample_content, "message": "v1"})
        client.post("/api/v1/prompts/versioned/versions", json={"content": {"sections": []}, "message": "v2"})
        resp = client.post("/api/v1/prompts/versioned/rollback", json={"version": 1})
        assert resp.status_code == 200
        assert resp.json()["version"] == 3
        assert resp.json()["content"] == sample_content
