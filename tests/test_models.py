"""Tests for Pydantic model validation."""

import pytest
from pydantic import ValidationError

from prompt_forge.api.models import ComposeRequest, PromptCreate, UsageLogCreate


class TestPromptCreate:
    def test_valid(self):
        p = PromptCreate(slug="my-prompt", name="My Prompt", type="persona")
        assert p.slug == "my-prompt"

    def test_invalid_slug(self):
        with pytest.raises(ValidationError):
            PromptCreate(slug="UPPER", name="X", type="persona")

    def test_invalid_type(self):
        with pytest.raises(ValidationError):
            PromptCreate(slug="ok-slug", name="X", type="invalid")

    def test_slug_too_short(self):
        with pytest.raises(ValidationError):
            PromptCreate(slug="a", name="X", type="persona")


class TestComposeRequest:
    def test_defaults(self):
        r = ComposeRequest(persona="code-reviewer")
        assert r.skills == []
        assert r.constraints == []
        assert r.branch == "main"
        assert r.strategy == "latest"

    def test_full(self):
        r = ComposeRequest(
            persona="code-reviewer",
            skills=["python"],
            constraints=["concise"],
            variables={"x": "y"},
            branch="experiment",
            strategy="pinned",
        )
        assert len(r.skills) == 1


class TestUsageLogCreate:
    def test_valid_outcome(self):
        from uuid import uuid4

        u = UsageLogCreate(
            prompt_id=uuid4(),
            version_id=uuid4(),
            agent_id="worker-1",
            outcome="success",
        )
        assert u.outcome == "success"

    def test_invalid_outcome(self):
        from uuid import uuid4

        with pytest.raises(ValidationError):
            UsageLogCreate(
                prompt_id=uuid4(),
                version_id=uuid4(),
                agent_id="worker-1",
                outcome="bad",
            )
