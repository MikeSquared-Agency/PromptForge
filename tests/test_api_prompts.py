"""Tests for prompt API endpoints."""


class TestPromptAPI:
    def test_create_prompt(self, client):
        resp = client.post("/api/v1/prompts", json={
            "slug": "test-prompt", "name": "Test", "type": "persona",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["slug"] == "test-prompt"

    def test_create_duplicate(self, client):
        client.post("/api/v1/prompts", json={"slug": "dupe", "name": "A", "type": "persona"})
        resp = client.post("/api/v1/prompts", json={"slug": "dupe", "name": "B", "type": "persona"})
        assert resp.status_code == 409

    def test_list_prompts(self, client):
        client.post("/api/v1/prompts", json={"slug": "aa", "name": "A", "type": "persona"})
        client.post("/api/v1/prompts", json={"slug": "bb", "name": "B", "type": "skill"})
        resp = client.get("/api/v1/prompts")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_filter_type(self, client):
        client.post("/api/v1/prompts", json={"slug": "aa", "name": "A", "type": "persona"})
        client.post("/api/v1/prompts", json={"slug": "bb", "name": "B", "type": "skill"})
        resp = client.get("/api/v1/prompts?type=skill")
        assert len(resp.json()) == 1

    def test_get_prompt(self, client):
        client.post("/api/v1/prompts", json={"slug": "getter", "name": "G", "type": "persona"})
        resp = client.get("/api/v1/prompts/getter")
        assert resp.status_code == 200
        assert resp.json()["slug"] == "getter"

    def test_get_not_found(self, client):
        resp = client.get("/api/v1/prompts/nonexistent")
        assert resp.status_code == 404

    def test_update_prompt(self, client):
        client.post("/api/v1/prompts", json={"slug": "updater", "name": "Old", "type": "persona"})
        resp = client.put("/api/v1/prompts/updater", json={"name": "New"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"

    def test_archive_prompt(self, client):
        client.post("/api/v1/prompts", json={"slug": "archiver", "name": "X", "type": "persona"})
        resp = client.delete("/api/v1/prompts/archiver")
        assert resp.status_code == 204

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
