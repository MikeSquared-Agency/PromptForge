"""Tests for composition API endpoints."""


class TestComposeAPI:
    def _seed(self, client, sample_content):
        client.post(
            "/api/v1/prompts", json={"slug": "reviewer", "name": "Reviewer", "type": "persona"}
        )
        client.post(
            "/api/v1/prompts/reviewer/versions",
            json={
                "content": sample_content,
                "message": "init",
            },
        )
        client.post(
            "/api/v1/prompts", json={"slug": "python-skill", "name": "Python", "type": "skill"}
        )
        client.post(
            "/api/v1/prompts/python-skill/versions",
            json={
                "content": {"sections": [{"id": "main", "content": "Expert in Python."}]},
                "message": "init",
            },
        )

    def test_compose(self, client, sample_content):
        self._seed(client, sample_content)
        resp = client.post(
            "/api/v1/compose",
            json={
                "persona": "reviewer",
                "skills": ["python-skill"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "prompt" in data
        assert len(data["manifest"]["components"]) == 2

    def test_compose_missing_persona(self, client):
        resp = client.post("/api/v1/compose", json={"persona": "nonexistent"})
        assert resp.status_code in (404, 422, 500)  # ValueError from resolver
