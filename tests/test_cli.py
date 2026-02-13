"""Tests for the forge CLI."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from prompt_forge.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client():
    with patch("prompt_forge.cli.main.ForgeClient") as MockClass:
        client = MagicMock()
        MockClass.return_value = client
        yield client


class TestPromptCommands:
    def test_prompt_list(self, runner, mock_client):
        mock_client.list_prompts.return_value = [
            {"slug": "test", "name": "Test", "type": "persona", "tags": [], "parent_slug": None}
        ]
        result = runner.invoke(cli, ["prompt", "list"])
        assert result.exit_code == 0
        assert "test" in result.output

    def test_prompt_create(self, runner, mock_client):
        mock_client.create_prompt.return_value = {"slug": "new-prompt", "name": "New"}
        result = runner.invoke(
            cli, ["prompt", "create", "--slug", "new-prompt", "--name", "New", "--type", "persona"]
        )
        assert result.exit_code == 0
        mock_client.create_prompt.assert_called_once()

    def test_prompt_show(self, runner, mock_client):
        mock_client.get_prompt.return_value = {"slug": "test", "name": "Test", "type": "persona"}
        result = runner.invoke(cli, ["prompt", "show", "test"])
        assert result.exit_code == 0
        assert "test" in result.output

    def test_prompt_archive(self, runner, mock_client):
        result = runner.invoke(cli, ["prompt", "archive", "test"])
        assert result.exit_code == 0
        mock_client.archive_prompt.assert_called_once_with("test")
        assert "Archived" in result.output


class TestVersionCommands:
    def test_version_history(self, runner, mock_client):
        mock_client.list_versions.return_value = [
            {
                "version": 1,
                "message": "init",
                "author": "sys",
                "branch": "main",
                "created_at": "2025-01-01",
            }
        ]
        result = runner.invoke(cli, ["version", "history", "test"])
        assert result.exit_code == 0
        assert "init" in result.output

    def test_version_commit_from_stdin(self, runner, mock_client):
        mock_client.commit_version.return_value = {"version": 2, "message": "update"}
        content = json.dumps({"sections": [], "variables": {}, "metadata": {}})
        result = runner.invoke(cli, ["version", "commit", "test", "-m", "update"], input=content)
        assert result.exit_code == 0
        mock_client.commit_version.assert_called_once()

    def test_version_diff(self, runner, mock_client):
        mock_client.diff_versions.return_value = {"changes": [], "summary": "No changes"}
        result = runner.invoke(cli, ["version", "diff", "test", "1", "2"])
        assert result.exit_code == 0

    def test_version_rollback(self, runner, mock_client):
        mock_client.rollback.return_value = {"version": 3, "message": "Rollback to version 1"}
        result = runner.invoke(cli, ["version", "rollback", "test", "1"])
        assert result.exit_code == 0


class TestComposeCommand:
    def test_compose(self, runner, mock_client):
        mock_client.compose.return_value = {
            "prompt": "You are a helpful assistant.",
            "manifest": {},
            "warnings": [],
        }
        result = runner.invoke(cli, ["compose", "--persona", "helper"])
        assert result.exit_code == 0
        assert "helpful assistant" in result.output

    def test_compose_with_warnings(self, runner, mock_client):
        mock_client.compose.return_value = {
            "prompt": "Text",
            "manifest": {},
            "warnings": ["Unresolved variables: name"],
        }
        result = runner.invoke(cli, ["compose", "--persona", "helper"])
        assert result.exit_code == 0


class TestSearchCommand:
    def test_search(self, runner, mock_client):
        mock_client.search.return_value = [
            {"slug": "found", "name": "Found", "type": "persona", "tags": ["ai"]}
        ]
        result = runner.invoke(cli, ["search", "found"])
        assert result.exit_code == 0
        assert "found" in result.output


class TestJsonOutput:
    def test_json_format(self, runner, mock_client):
        mock_client.list_prompts.return_value = [{"slug": "test", "name": "Test"}]
        result = runner.invoke(cli, ["--format", "json", "prompt", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
