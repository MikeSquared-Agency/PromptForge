"""Tests for persona prompt API endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_persona_prompt_latest_not_found(client: TestClient):
    """Test getting latest persona prompt when it doesn't exist."""
    response = client.get("/api/v1/persona-prompts/nonexistent")
    assert response.status_code == 404
    assert response.json()["detail"] == "Persona 'nonexistent' not found"


def test_get_persona_prompt_version_not_found(client: TestClient):
    """Test getting specific persona prompt version when it doesn't exist."""
    response = client.get("/api/v1/persona-prompts/nonexistent/1")
    assert response.status_code == 404
    assert response.json()["detail"] == "Persona 'nonexistent' version 1 not found"


def test_create_persona_prompt_version(client: TestClient):
    """Test creating a persona prompt version."""
    template = "You are a developer. Context: {{context}}"

    response = client.post("/api/v1/persona-prompts/developer", json={"template": template})

    assert response.status_code == 201
    data = response.json()
    assert data["persona"] == "developer"
    assert data["version"] == 1
    assert data["template"] == template
    assert data["is_latest"] is True
    assert "id" in data
    assert "created_at" in data


def test_get_persona_prompt_latest_after_create(client: TestClient):
    """Test getting latest persona prompt after creating one."""
    template = "You are a tester. Context: {{context}}"

    # Create the persona prompt
    create_response = client.post("/api/v1/persona-prompts/tester", json={"template": template})
    assert create_response.status_code == 201

    # Get the latest version
    response = client.get("/api/v1/persona-prompts/tester")
    assert response.status_code == 200
    data = response.json()
    assert data["persona"] == "tester"
    assert data["version"] == 1
    assert data["template"] == template
    assert data["is_latest"] is True


def test_get_persona_prompt_specific_version(client: TestClient):
    """Test getting a specific version of a persona prompt."""
    template = "You are a reviewer. Context: {{context}}"

    # Create the persona prompt
    client.post("/api/v1/persona-prompts/reviewer", json={"template": template})

    # Get the specific version
    response = client.get("/api/v1/persona-prompts/reviewer/1")
    assert response.status_code == 200
    data = response.json()
    assert data["persona"] == "reviewer"
    assert data["version"] == 1
    assert data["template"] == template


def test_create_multiple_versions(client: TestClient, app):
    """Test creating multiple versions of a persona prompt."""
    # We need to mock the bulk update operation for this test
    from prompt_forge.db.client import get_supabase_client

    def mock_update_previous_versions(client, mock_db):
        """Helper to mock the bulk update operation."""
        for row in mock_db._tables["persona_prompts"]:
            if row["persona"] == "architect" and not row.get("version") == 2:
                row["is_latest"] = False

    mock_db = app.dependency_overrides[get_supabase_client]()

    template1 = "You are an architect v1. Context: {{context}}"
    template2 = "You are an architect v2. Context: {{context}}"

    # Create first version
    response1 = client.post("/api/v1/persona-prompts/architect", json={"template": template1})
    assert response1.status_code == 201
    data1 = response1.json()
    assert data1["version"] == 1

    # Mock the bulk update
    mock_update_previous_versions(client, mock_db)

    # Create second version
    response2 = client.post("/api/v1/persona-prompts/architect", json={"template": template2})
    assert response2.status_code == 201
    data2 = response2.json()
    assert data2["version"] == 2

    # Latest should be version 2
    latest_response = client.get("/api/v1/persona-prompts/architect")
    assert latest_response.status_code == 200
    latest_data = latest_response.json()
    assert latest_data["version"] == 2
    assert latest_data["template"] == template2


def test_list_persona_prompt_versions(client: TestClient, app):
    """Test listing all versions of a persona prompt."""
    from prompt_forge.db.client import get_supabase_client

    mock_db = app.dependency_overrides[get_supabase_client]()

    templates = ["Version 1", "Version 2", "Version 3"]

    for i, template in enumerate(templates, 1):
        # Mock the bulk update for previous versions
        for row in mock_db._tables["persona_prompts"]:
            if row["persona"] == "researcher" and row["version"] < i:
                row["is_latest"] = False

        client.post("/api/v1/persona-prompts/researcher", json={"template": template})

    response = client.get("/api/v1/persona-prompts/researcher/versions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3

    # Should be ordered by version descending
    assert data[0]["version"] == 3
    assert data[1]["version"] == 2
    assert data[2]["version"] == 1


def test_list_persona_prompt_versions_not_found(client: TestClient):
    """Test listing versions for non-existent persona."""
    response = client.get("/api/v1/persona-prompts/nonexistent/versions")
    assert response.status_code == 404
    assert response.json()["detail"] == "Persona 'nonexistent' not found"


def test_seed_initial_personas(client: TestClient):
    """Test seeding initial personas."""
    response = client.post("/api/v1/persona-prompts/seed")
    assert response.status_code == 201
    assert response.json()["message"] == "Initial personas seeded successfully"

    # Verify that personas were created
    expected_personas = ["researcher", "developer", "reviewer", "tester", "architect"]

    for persona in expected_personas:
        get_response = client.get(f"/api/v1/persona-prompts/{persona}")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["version"] == 1
        assert data["is_latest"] is True
        # Check that template contains expected placeholders
        template = data["template"]
        assert "{{objective}}" in template
        assert "{{context}}" in template
        assert "{{constraints}}" in template
        assert "{{scope_paths}}" in template
        assert "{{alexandria_context}}" in template


def test_create_persona_prompt_empty_template(client: TestClient):
    """Test creating persona prompt with empty template fails validation."""
    response = client.post("/api/v1/persona-prompts/empty", json={"template": ""})
    assert response.status_code == 422  # Validation error


def test_create_persona_prompt_missing_template(client: TestClient):
    """Test creating persona prompt without template fails validation."""
    response = client.post("/api/v1/persona-prompts/missing", json={})
    assert response.status_code == 422  # Validation error
