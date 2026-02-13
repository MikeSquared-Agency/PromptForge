"""End-to-end tests for the version safety spec.

These tests simulate realistic agent workflows exercising the full
PATCH, regression guard, diff, and restore pipeline through the API.
"""


class TestPatchWorkflow:
    """Agent uses PATCH to safely add fields without nuking content."""

    def _setup_persona(self, client):
        client.post("/api/v1/prompts", json={
            "slug": "kai-soul", "name": "Kai Soul", "type": "persona",
        })
        content = {
            "identity": "You are Kai, an AI assistant for deep conversations.",
            "voice": "Warm, curious, empathetic. Uses metaphors.",
            "personality": "Thoughtful and reflective. Asks probing questions.",
            "principles": ["Be honest", "Be kind", "Respect boundaries"],
            "constraints": ["No medical advice", "No legal advice"],
            "capabilities": "Deep conversation, emotional support, creative writing.",
        }
        resp = client.post("/api/v1/prompts/kai-soul/versions", json={
            "content": content, "message": "Initial soul definition", "author": "mike",
        })
        assert resp.status_code == 201
        return content

    def test_agent_adds_slack_fields_via_patch(self, client):
        """An agent adds Slack config without touching the soul fields."""
        original = self._setup_persona(client)

        resp = client.patch("/api/v1/prompts/kai-soul/versions", json={
            "content": {
                "slack_identity": "Slack User ID: U0AE9ME4SNB",
                "slack_rules": "Always append footer with emoji.",
            },
            "message": "Add Slack identity and rules",
            "author": "kai",
        })
        assert resp.status_code == 201
        v2 = resp.json()
        assert v2["version"] == 2

        # All original fields preserved
        for key in original:
            assert key in v2["content"], f"Original field '{key}' was lost"
            assert v2["content"][key] == original[key]

        # New fields added
        assert v2["content"]["slack_identity"] == "Slack User ID: U0AE9ME4SNB"
        assert v2["content"]["slack_rules"] == "Always append footer with emoji."

    def test_multiple_patches_accumulate(self, client):
        """Multiple PATCH calls accumulate fields."""
        self._setup_persona(client)

        client.patch("/api/v1/prompts/kai-soul/versions", json={
            "content": {"slack_identity": "U123"}, "message": "Add slack", "author": "kai",
        })
        resp = client.patch("/api/v1/prompts/kai-soul/versions", json={
            "content": {"discord_identity": "kai#1234"}, "message": "Add discord", "author": "kai",
        })
        assert resp.status_code == 201
        v3 = resp.json()
        assert v3["version"] == 3
        assert "identity" in v3["content"]
        assert "slack_identity" in v3["content"]
        assert "discord_identity" in v3["content"]

    def test_patch_updates_existing_field(self, client):
        """PATCH can update a field's value."""
        self._setup_persona(client)

        resp = client.patch("/api/v1/prompts/kai-soul/versions", json={
            "content": {"voice": "Formal and precise. Avoids metaphors."},
            "message": "Change voice to formal",
            "author": "mike",
        })
        assert resp.status_code == 201
        assert resp.json()["content"]["voice"] == "Formal and precise. Avoids metaphors."
        assert resp.json()["content"]["identity"].startswith("You are Kai")

    def test_patch_no_versions_returns_404(self, client):
        """PATCH on a prompt with no versions gives clear error."""
        client.post("/api/v1/prompts", json={
            "slug": "empty-prompt", "name": "Empty", "type": "persona",
        })
        resp = client.patch("/api/v1/prompts/empty-prompt/versions", json={
            "content": {"a": "b"}, "message": "patch",
        })
        assert resp.status_code == 404
        assert "use post" in resp.json()["detail"].lower()


class TestRegressionGuardE2E:
    """Regression guard prevents accidental content loss end-to-end."""

    def _setup_with_content(self, client):
        client.post("/api/v1/prompts", json={
            "slug": "guarded", "name": "Guarded", "type": "persona",
        })
        content = {
            "identity": "Deep identity description " * 10,
            "voice": "Voice style " * 10,
            "personality": "Personality traits " * 10,
            "principles": ["P1", "P2", "P3", "P4", "P5"],
            "constraints": ["C1", "C2", "C3"],
            "capabilities": "Many capabilities " * 10,
        }
        client.post("/api/v1/prompts/guarded/versions", json={
            "content": content, "message": "v1", "author": "mike",
        })
        return content

    def test_post_with_missing_fields_blocked(self, client):
        """POST that drops most fields is blocked."""
        self._setup_with_content(client)

        resp = client.post("/api/v1/prompts/guarded/versions", json={
            "content": {"slack_id": "U123"},
            "message": "Oops, only sent new field",
            "author": "kai",
        })
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["error"] == "content_regression_blocked"
        assert "keys_removed" in detail["diff"]
        assert len(detail["diff"]["keys_removed"]) >= 5

    def test_post_with_acknowledge_bypasses_block(self, client):
        """POST with acknowledge_reduction: true bypasses the guard."""
        self._setup_with_content(client)

        resp = client.post("/api/v1/prompts/guarded/versions", json={
            "content": {"slack_id": "U123"},
            "message": "Intentional rewrite",
            "author": "mike",
            "acknowledge_reduction": True,
        })
        assert resp.status_code == 201
        assert resp.json()["warnings"] is not None
        assert len(resp.json()["warnings"]) > 0

    def test_first_version_never_blocked(self, client):
        """First version of a prompt should never trigger regression guard."""
        client.post("/api/v1/prompts", json={
            "slug": "brand-new", "name": "New", "type": "persona",
        })
        resp = client.post("/api/v1/prompts/brand-new/versions", json={
            "content": {"identity": "I am new"},
            "message": "first",
            "author": "mike",
        })
        assert resp.status_code == 201
        assert resp.json()["warnings"] is None

    def test_identical_content_no_warning(self, client):
        """Posting same content again should not trigger warnings."""
        content = {"identity": "Same", "voice": "Same"}
        client.post("/api/v1/prompts", json={
            "slug": "stable", "name": "Stable", "type": "persona",
        })
        client.post("/api/v1/prompts/stable/versions", json={
            "content": content, "message": "v1",
        })
        resp = client.post("/api/v1/prompts/stable/versions", json={
            "content": content, "message": "v2",
        })
        assert resp.status_code == 201
        assert resp.json()["warnings"] is None

    def test_block_response_includes_diff_details(self, client):
        """The 409 response includes actionable diff information."""
        self._setup_with_content(client)

        resp = client.post("/api/v1/prompts/guarded/versions", json={
            "content": {"identity": "short"},
            "message": "bad update",
        })
        assert resp.status_code == 409
        diff = resp.json()["detail"]["diff"]
        assert "keys_removed" in diff
        assert "keys_added" in diff
        assert "keys_unchanged" in diff
        assert "parent_version" in diff
        assert diff["parent_version"] == 1
        assert "content_reduction_pct" in diff


class TestFieldDiffE2E:
    """Diff endpoint for debugging version changes."""

    def _create_versions(self, client):
        client.post("/api/v1/prompts", json={
            "slug": "diffable", "name": "D", "type": "persona",
        })
        v1 = {"identity": "Kai v1", "voice": "Warm", "principles": ["Be kind"]}
        v2 = {"identity": "Kai v2", "voice": "Warm", "slack_id": "U123"}
        client.post("/api/v1/prompts/diffable/versions", json={
            "content": v1, "message": "v1",
        })
        client.post("/api/v1/prompts/diffable/versions", json={
            "content": v2, "message": "v2", "acknowledge_reduction": True,
        })

    def test_diff_shows_all_change_types(self, client):
        self._create_versions(client)
        resp = client.get("/api/v1/prompts/diffable/versions/1/diff/2")
        assert resp.status_code == 200
        data = resp.json()
        actions = {c["field"]: c["action"] for c in data["changes"]}
        assert "principles" in actions and actions["principles"] == "removed"
        assert "slack_id" in actions and actions["slack_id"] == "added"
        assert "identity" in actions and actions["identity"] == "modified"
        assert data["summary"]["unchanged"] == 1  # voice

    def test_diff_reverse_direction(self, client):
        """Diffing in reverse shows opposite actions."""
        self._create_versions(client)
        resp = client.get("/api/v1/prompts/diffable/versions/2/diff/1")
        assert resp.status_code == 200
        actions = {c["field"]: c["action"] for c in resp.json()["changes"]}
        assert actions["principles"] == "added"  # was removed v1→v2, so added v2→v1
        assert actions["slack_id"] == "removed"

    def test_diff_nonexistent_version_404(self, client):
        self._create_versions(client)
        resp = client.get("/api/v1/prompts/diffable/versions/1/diff/99")
        assert resp.status_code == 404

    def test_diff_same_version_no_changes(self, client):
        self._create_versions(client)
        resp = client.get("/api/v1/prompts/diffable/versions/1/diff/1")
        assert resp.status_code == 200
        assert resp.json()["summary"]["modified"] == 0
        assert resp.json()["summary"]["added"] == 0
        assert resp.json()["summary"]["removed"] == 0


class TestRestoreE2E:
    """Restore endpoint for recovering from accidental content loss."""

    def _setup_with_loss(self, client):
        """Create v1 (full), v2 (broken) to simulate accidental nuke."""
        client.post("/api/v1/prompts", json={
            "slug": "restore-me", "name": "R", "type": "persona",
        })
        full = {
            "identity": "Full identity with lots of detail.",
            "voice": "Warm and empathetic.",
            "principles": ["Be kind", "Be honest"],
            "capabilities": "Deep conversation.",
        }
        broken = {
            "identity": "Short.",
            "slack_id": "U123",
        }
        client.post("/api/v1/prompts/restore-me/versions", json={
            "content": full, "message": "v1 - complete soul", "author": "mike",
        })
        client.post("/api/v1/prompts/restore-me/versions", json={
            "content": broken, "message": "v2 - oops", "acknowledge_reduction": True,
        })
        return full

    def test_restore_exact(self, client):
        """Restore v1 exactly, creating v3."""
        full = self._setup_with_loss(client)
        resp = client.post("/api/v1/prompts/restore-me/versions/restore", json={
            "from_version": 1, "author": "mike",
        })
        assert resp.status_code == 201
        assert resp.json()["version"] == 3
        assert resp.json()["content"] == full

    def test_restore_with_merge(self, client):
        """Restore v1 + merge v2's Slack field."""
        full = self._setup_with_loss(client)
        resp = client.post("/api/v1/prompts/restore-me/versions/restore", json={
            "from_version": 1,
            "patch": {"slack_id": "U123"},
            "message": "Restore v1 + Slack config",
            "author": "mike",
        })
        assert resp.status_code == 201
        v3 = resp.json()
        # All v1 fields present
        for key in full:
            assert key in v3["content"]
        # Plus the merged field
        assert v3["content"]["slack_id"] == "U123"

    def test_restore_nonexistent_version_404(self, client):
        self._setup_with_loss(client)
        resp = client.post("/api/v1/prompts/restore-me/versions/restore", json={
            "from_version": 99,
        })
        assert resp.status_code == 404

    def test_restore_default_message(self, client):
        """Default message includes the source version number."""
        self._setup_with_loss(client)
        resp = client.post("/api/v1/prompts/restore-me/versions/restore", json={
            "from_version": 1,
        })
        assert "version 1" in resp.json()["message"].lower()


class TestFullAgentWorkflow:
    """End-to-end: simulate the exact scenario from the spec."""

    def test_spec_scenario(self, client):
        """
        1. Mike creates persona with full soul (v1)
        2. Agent adds Slack fields via PATCH (v2) — soul preserved
        3. Bad agent tries POST with only new fields — BLOCKED
        4. Diff v1 vs v2 shows only additions
        5. Agent patches voice update (v3) — everything still intact
        """
        # Step 1: Create full persona
        client.post("/api/v1/prompts", json={
            "slug": "kai", "name": "Kai", "type": "persona",
        })
        soul = {
            "identity": "You are Kai, an AI persona for deep conversations.",
            "voice": "Warm, curious, uses metaphors and asks probing questions.",
            "personality": "Thoughtful, empathetic, intellectually curious.",
            "principles": ["Honesty", "Kindness", "Respect boundaries", "Growth mindset"],
            "constraints": ["No medical advice", "No legal advice", "No financial advice"],
            "capabilities": "Deep conversation, emotional support, creative writing.",
        }
        r1 = client.post("/api/v1/prompts/kai/versions", json={
            "content": soul, "message": "Initial soul", "author": "mike",
        })
        assert r1.status_code == 201
        assert r1.json()["version"] == 1

        # Step 2: Agent PATCHes in Slack fields
        r2 = client.patch("/api/v1/prompts/kai/versions", json={
            "content": {
                "slack_identity": "Slack User ID: U0AE9ME4SNB",
                "slack_rules": "Always append footer with kaomoji.",
            },
            "message": "Add Slack identity and rules",
            "author": "kai",
        })
        assert r2.status_code == 201
        assert r2.json()["version"] == 2
        v2_content = r2.json()["content"]
        # Soul preserved
        assert v2_content["identity"] == soul["identity"]
        assert v2_content["voice"] == soul["voice"]
        assert v2_content["principles"] == soul["principles"]
        # Slack added
        assert "slack_identity" in v2_content

        # Step 3: Bad agent tries full POST with only Slack fields
        r3 = client.post("/api/v1/prompts/kai/versions", json={
            "content": {
                "slack_identity": "Slack User ID: U0AE9ME4SNB",
                "slack_rules": "Always append footer with kaomoji.",
            },
            "message": "Updating Slack config",
            "author": "bad-agent",
        })
        assert r3.status_code == 409
        assert r3.json()["detail"]["error"] == "content_regression_blocked"

        # Step 4: Diff v1 vs v2 — only additions, no removals
        r4 = client.get("/api/v1/prompts/kai/versions/1/diff/2")
        assert r4.status_code == 200
        diff = r4.json()
        actions = {c["field"]: c["action"] for c in diff["changes"]}
        assert "slack_identity" in actions and actions["slack_identity"] == "added"
        assert "slack_rules" in actions and actions["slack_rules"] == "added"
        assert diff["summary"]["removed"] == 0
        assert diff["summary"]["added"] == 2

        # Step 5: Agent patches a voice update
        r5 = client.patch("/api/v1/prompts/kai/versions", json={
            "content": {"voice": "Formal and precise. Avoids colloquialisms."},
            "message": "Shift to formal voice",
            "author": "kai",
        })
        assert r5.status_code == 201
        assert r5.json()["version"] == 3
        v3_content = r5.json()["content"]
        # Voice updated
        assert v3_content["voice"] == "Formal and precise. Avoids colloquialisms."
        # Everything else still intact
        assert v3_content["identity"] == soul["identity"]
        assert v3_content["principles"] == soul["principles"]
        assert v3_content["slack_identity"] == "Slack User ID: U0AE9ME4SNB"
