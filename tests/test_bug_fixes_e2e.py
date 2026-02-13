"""End-to-end tests for the PromptForge Fixes spec.

Bug 1: JSON control characters in version content must produce valid JSON.
Bug 2: GET /versions/latest must work without 422 errors.
Bug 3: Soul boot pipeline handles both sections-format and flat JSON content.
"""

import json


class TestControlCharsE2E:
    """Bug 1: Content with newlines, tabs, carriage returns must round-trip
    through the API and produce valid, parseable JSON responses."""

    def _create_prompt(self, client, slug="ctrl-chars"):
        client.post(
            "/api/v1/prompts",
            json={
                "slug": slug,
                "name": "Control Chars Test",
                "type": "persona",
            },
        )

    def test_newlines_in_voice_field(self, client):
        """Newlines in content fields survive create → fetch cycle."""
        self._create_prompt(client)
        content = {
            "voice": "Warm and empathetic.\nUses metaphors.\nAsks probing questions.",
            "identity": "You are Kai.",
        }
        client.post(
            "/api/v1/prompts/ctrl-chars/versions",
            json={
                "content": content,
                "message": "v1",
            },
        )
        resp = client.get("/api/v1/prompts/ctrl-chars/versions/latest")
        assert resp.status_code == 200
        raw = resp.content.decode("utf-8")
        parsed = json.loads(raw)
        assert parsed["content"]["voice"] == content["voice"]

    def test_tabs_in_content(self, client):
        """Tabs in content are properly escaped in JSON output."""
        self._create_prompt(client, "tab-test")
        content = {"instructions": "Step 1\tDo this\tStep 2\tDo that"}
        client.post(
            "/api/v1/prompts/tab-test/versions",
            json={
                "content": content,
                "message": "v1",
            },
        )
        resp = client.get("/api/v1/prompts/tab-test/versions/latest")
        assert resp.status_code == 200
        parsed = json.loads(resp.content.decode("utf-8"))
        assert parsed["content"]["instructions"] == content["instructions"]

    def test_carriage_returns_in_content(self, client):
        """Carriage returns (\\r\\n) are properly handled."""
        self._create_prompt(client, "cr-test")
        content = {"identity": "You are Kai.\r\nA helpful assistant.\r\nBe kind."}
        client.post(
            "/api/v1/prompts/cr-test/versions",
            json={
                "content": content,
                "message": "v1",
            },
        )
        resp = client.get("/api/v1/prompts/cr-test/versions/latest")
        assert resp.status_code == 200
        parsed = json.loads(resp.content.decode("utf-8"))
        assert parsed["content"]["identity"] == content["identity"]

    def test_control_chars_in_list_endpoint(self, client):
        """List versions endpoint also produces valid JSON with control chars."""
        self._create_prompt(client, "list-ctrl")
        content = {"voice": "Line 1\nLine 2\n\tIndented line 3"}
        client.post(
            "/api/v1/prompts/list-ctrl/versions",
            json={
                "content": content,
                "message": "v1",
            },
        )
        resp = client.get("/api/v1/prompts/list-ctrl/versions")
        assert resp.status_code == 200
        parsed = json.loads(resp.content.decode("utf-8"))
        assert parsed[0]["content"]["voice"] == content["voice"]

    def test_mixed_control_chars_across_fields(self, client):
        """Multiple fields with different control characters all round-trip."""
        self._create_prompt(client, "mixed-ctrl")
        content = {
            "identity": "Kai\r\nAssistant",
            "voice": "Warm\tand\tkind",
            "principles": ["Be honest\nAlways", "Be kind\tTo all"],
        }
        client.post(
            "/api/v1/prompts/mixed-ctrl/versions",
            json={
                "content": content,
                "message": "v1",
            },
        )
        resp = client.get("/api/v1/prompts/mixed-ctrl/versions/latest")
        assert resp.status_code == 200
        parsed = json.loads(resp.content.decode("utf-8"))
        assert parsed["content"] == content

    def test_control_chars_survive_patch(self, client):
        """PATCH merge preserves control characters in existing content."""
        self._create_prompt(client, "patch-ctrl")
        content = {"voice": "Line 1\nLine 2\nLine 3", "identity": "Kai"}
        client.post(
            "/api/v1/prompts/patch-ctrl/versions",
            json={
                "content": content,
                "message": "v1",
            },
        )
        resp = client.patch(
            "/api/v1/prompts/patch-ctrl/versions",
            json={
                "content": {"slack_id": "U123"},
                "message": "add slack",
            },
        )
        assert resp.status_code == 201
        parsed = json.loads(resp.content.decode("utf-8"))
        assert parsed["content"]["voice"] == "Line 1\nLine 2\nLine 3"
        assert parsed["content"]["slack_id"] == "U123"

    def test_control_chars_in_diff_endpoint(self, client):
        """Diff endpoint works on content containing control characters."""
        self._create_prompt(client, "diff-ctrl")
        v1 = {"voice": "Line 1\nLine 2", "identity": "Kai"}
        v2 = {"voice": "Updated\nVoice", "identity": "Kai", "slack": "U1"}
        client.post(
            "/api/v1/prompts/diff-ctrl/versions",
            json={
                "content": v1,
                "message": "v1",
            },
        )
        client.post(
            "/api/v1/prompts/diff-ctrl/versions",
            json={
                "content": v2,
                "message": "v2",
            },
        )
        resp = client.get("/api/v1/prompts/diff-ctrl/versions/1/diff/2")
        assert resp.status_code == 200
        data = resp.json()
        actions = {c["field"]: c["action"] for c in data["changes"]}
        assert actions["voice"] == "modified"
        assert actions["slack"] == "added"


class TestLatestEndpointE2E:
    """Bug 2: /versions/latest must be routable and return the most recent
    version without conflicting with /versions/{version:int}."""

    def _create_prompt(self, client, slug="latest-test"):
        client.post(
            "/api/v1/prompts",
            json={
                "slug": slug,
                "name": "Latest Test",
                "type": "persona",
            },
        )

    def test_latest_returns_most_recent_after_multiple_versions(self, client):
        """After creating 3 versions, /latest returns v3."""
        self._create_prompt(client)
        for i in range(1, 4):
            client.post(
                "/api/v1/prompts/latest-test/versions",
                json={
                    "content": {"version_num": i},
                    "message": f"v{i}",
                },
            )
        resp = client.get("/api/v1/prompts/latest-test/versions/latest")
        assert resp.status_code == 200
        assert resp.json()["version"] == 3
        assert resp.json()["content"]["version_num"] == 3

    def test_latest_updates_after_new_version(self, client):
        """/latest reflects newly created versions immediately."""
        self._create_prompt(client, "latest-live")
        client.post(
            "/api/v1/prompts/latest-live/versions",
            json={
                "content": {"state": "initial"},
                "message": "v1",
            },
        )
        resp1 = client.get("/api/v1/prompts/latest-live/versions/latest")
        assert resp1.json()["version"] == 1

        client.post(
            "/api/v1/prompts/latest-live/versions",
            json={
                "content": {"state": "updated"},
                "message": "v2",
            },
        )
        resp2 = client.get("/api/v1/prompts/latest-live/versions/latest")
        assert resp2.json()["version"] == 2
        assert resp2.json()["content"]["state"] == "updated"

    def test_latest_and_integer_routes_coexist(self, client):
        """/versions/latest and /versions/1 both work without conflict."""
        self._create_prompt(client, "coexist")
        client.post(
            "/api/v1/prompts/coexist/versions",
            json={
                "content": {"identity": "v1 content"},
                "message": "v1",
            },
        )
        client.post(
            "/api/v1/prompts/coexist/versions",
            json={
                "content": {"identity": "v2 content"},
                "message": "v2",
            },
        )

        # Integer route
        resp_int = client.get("/api/v1/prompts/coexist/versions/1")
        assert resp_int.status_code == 200
        assert resp_int.json()["version"] == 1
        assert resp_int.json()["content"]["identity"] == "v1 content"

        # Latest route
        resp_latest = client.get("/api/v1/prompts/coexist/versions/latest")
        assert resp_latest.status_code == 200
        assert resp_latest.json()["version"] == 2
        assert resp_latest.json()["content"]["identity"] == "v2 content"

    def test_latest_404_when_no_versions(self, client):
        """/versions/latest returns 404 when prompt has no versions."""
        self._create_prompt(client, "empty-latest")
        resp = client.get("/api/v1/prompts/empty-latest/versions/latest")
        assert resp.status_code == 404

    def test_latest_404_when_prompt_missing(self, client):
        """/versions/latest returns 404 for nonexistent prompt."""
        resp = client.get("/api/v1/prompts/nonexistent/versions/latest")
        assert resp.status_code == 404

    def test_latest_auto_subscribes_agent(self, client):
        """/versions/latest with X-Agent-ID header creates a subscription."""
        self._create_prompt(client, "sub-latest")
        client.post(
            "/api/v1/prompts/sub-latest/versions",
            json={
                "content": {"identity": "Kai"},
                "message": "v1",
            },
        )
        resp = client.get(
            "/api/v1/prompts/sub-latest/versions/latest",
            headers={"X-Agent-ID": "scout"},
        )
        assert resp.status_code == 200

        # Verify subscription was created
        subs_resp = client.get("/api/v1/prompts/sub-latest/subscriptions")
        if subs_resp.status_code == 200:
            agents = [s["agent_id"] for s in subs_resp.json()]
            assert "scout" in agents


class TestSoulBootPipelineE2E:
    """Bug 3: The soul boot pipeline must handle both sections-format content
    and flat JSON content from PromptForge.

    These tests verify the API returns content that entrypoint scripts can parse.
    """

    def _create_prompt(self, client, slug="soul-test"):
        client.post(
            "/api/v1/prompts",
            json={
                "slug": slug,
                "name": "Soul Test",
                "type": "persona",
            },
        )

    def test_sections_format_via_latest(self, client):
        """Content with sections array is accessible via /latest."""
        self._create_prompt(client)
        content = {
            "sections": [
                {"id": "identity", "label": "Identity", "content": "You are Kai."},
                {"id": "voice", "label": "Voice", "content": "Warm and empathetic."},
            ],
        }
        client.post(
            "/api/v1/prompts/soul-test/versions",
            json={
                "content": content,
                "message": "v1",
            },
        )
        resp = client.get("/api/v1/prompts/soul-test/versions/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert "sections" in data["content"]
        assert len(data["content"]["sections"]) == 2
        assert data["content"]["sections"][0]["id"] == "identity"

    def test_flat_json_via_latest(self, client):
        """Flat key-value JSON (no sections) is accessible via /latest."""
        self._create_prompt(client, "flat-soul")
        content = {
            "identity": "You are Kai, a thoughtful assistant.",
            "voice": "Warm and empathetic.",
            "principles": ["Be kind", "Be honest"],
        }
        client.post(
            "/api/v1/prompts/flat-soul/versions",
            json={
                "content": content,
                "message": "v1",
            },
        )
        resp = client.get("/api/v1/prompts/flat-soul/versions/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"]["identity"] == content["identity"]
        assert data["content"]["voice"] == content["voice"]
        assert data["content"]["principles"] == content["principles"]

    def test_boot_pipeline_simulation_sections(self, client):
        """Simulate what an entrypoint script does: fetch latest, extract content,
        write SOUL.md from sections format."""
        self._create_prompt(client, "boot-sections")
        content = {
            "sections": [
                {"id": "identity", "content": "You are Scout."},
                {"id": "voice", "content": "Analytical and precise."},
                {"id": "constraints", "content": "Be concise."},
            ],
        }
        client.post(
            "/api/v1/prompts/boot-sections/versions",
            json={
                "content": content,
                "message": "v1",
            },
        )

        # Simulate entrypoint: fetch /latest, parse response
        resp = client.get("/api/v1/prompts/boot-sections/versions/latest")
        assert resp.status_code == 200
        raw = resp.content.decode("utf-8")
        data = json.loads(raw)

        # Extract content like the entrypoint does
        fetched_content = data.get("content", {})
        if isinstance(fetched_content, str):
            fetched_content = json.loads(fetched_content)

        sections = fetched_content.get("sections", [])
        assert len(sections) == 3

        # Build SOUL.md like the entrypoint does
        lines = []
        for s in sections:
            heading = s.get("id", "").replace("_", " ").title()
            lines.append(f"## {heading}")
            lines.append(s.get("content", ""))
            lines.append("")

        soul_md = "\n".join(lines)
        assert "## Identity" in soul_md
        assert "You are Scout." in soul_md
        assert "## Voice" in soul_md
        assert "## Constraints" in soul_md

    def test_boot_pipeline_simulation_flat_json(self, client):
        """Simulate what an entrypoint script does with flat JSON content
        (no sections array)."""
        self._create_prompt(client, "boot-flat")
        content = {
            "identity": "You are Celebrimbor, a code review agent.",
            "voice": "Direct and technical.",
            "principles": ["Security first", "Performance matters"],
            "constraints": "No hand-holding.",
        }
        client.post(
            "/api/v1/prompts/boot-flat/versions",
            json={
                "content": content,
                "message": "v1",
            },
        )

        resp = client.get("/api/v1/prompts/boot-flat/versions/latest")
        assert resp.status_code == 200
        raw = resp.content.decode("utf-8")
        data = json.loads(raw)

        fetched_content = data.get("content", {})
        if isinstance(fetched_content, str):
            fetched_content = json.loads(fetched_content)

        sections = fetched_content.get("sections", [])
        assert sections == [] or "sections" not in fetched_content

        # Build SOUL.md from flat keys like the entrypoint does
        lines = ["# Soul", ""]
        for key, value in fetched_content.items():
            heading = key.replace("_", " ").title()
            lines.append(f"## {heading}")
            if isinstance(value, list):
                for item in value:
                    lines.append(f"- {item}")
            elif isinstance(value, str):
                lines.append(value)
            else:
                lines.append(str(value))
            lines.append("")

        soul_md = "\n".join(lines)
        assert "## Identity" in soul_md
        assert "You are Celebrimbor" in soul_md
        assert "## Principles" in soul_md
        assert "- Security first" in soul_md
        assert "## Constraints" in soul_md

    def test_content_with_control_chars_in_boot_pipeline(self, client):
        """Content with newlines doesn't break the boot pipeline JSON parsing."""
        self._create_prompt(client, "boot-ctrl")
        content = {
            "identity": "You are Scout.\nA code review assistant.",
            "voice": "Direct\tand\tprecise.",
        }
        client.post(
            "/api/v1/prompts/boot-ctrl/versions",
            json={
                "content": content,
                "message": "v1",
            },
        )
        resp = client.get("/api/v1/prompts/boot-ctrl/versions/latest")
        assert resp.status_code == 200

        # Simulate the python3 -c inline script in entrypoints
        raw = resp.content.decode("utf-8")
        data = json.loads(raw)  # This is what breaks with Bug 1
        fetched_content = data.get("content", {})
        assert fetched_content["identity"] == content["identity"]
        assert fetched_content["voice"] == content["voice"]


class TestAllBugsIntegration:
    """Combined scenario exercising all three bug fixes together."""

    def test_full_agent_boot_cycle(self, client):
        """
        Simulate a full agent lifecycle:
        1. Create a soul with flat JSON containing control characters
        2. Add more versions
        3. Fetch /latest (Bug 2) — must not 422
        4. Response is valid JSON (Bug 1) — must be parseable
        5. Content is flat JSON (Bug 3) — entrypoint can handle it
        """
        # Create prompt and soul
        client.post(
            "/api/v1/prompts",
            json={
                "slug": "agent-boot",
                "name": "Boot Test",
                "type": "persona",
            },
        )
        soul = {
            "identity": "You are Scout, a senior code reviewer.\nYou specialize in Python and security.",
            "voice": "Analytical, direct.\tUses bullet points.",
            "principles": ["Security first", "Be concise\nBut thorough"],
            "constraints": "No hand-holding.\r\nExpect developer-level understanding.",
        }
        client.post(
            "/api/v1/prompts/agent-boot/versions",
            json={
                "content": soul,
                "message": "Initial soul",
                "author": "mike",
            },
        )

        # Agent adds fields via PATCH
        client.patch(
            "/api/v1/prompts/agent-boot/versions",
            json={
                "content": {"slack_id": "U0AE9ME4SNB"},
                "message": "Add Slack",
                "author": "scout",
            },
        )

        # Boot sequence: fetch latest
        resp = client.get("/api/v1/prompts/agent-boot/versions/latest")
        assert resp.status_code == 200  # Bug 2: no 422

        # Parse response body as JSON
        raw = resp.content.decode("utf-8")
        data = json.loads(raw)  # Bug 1: must not fail
        assert data["version"] == 2

        # Extract content for SOUL.md generation
        content = data["content"]
        assert isinstance(content, dict)  # Bug 1: must be dict, not string

        # Verify all fields present (PATCH preserved originals)
        assert "identity" in content
        assert "voice" in content
        assert "principles" in content
        assert "constraints" in content
        assert content["slack_id"] == "U0AE9ME4SNB"

        # Bug 3: Flat JSON — no sections key, entrypoint handles it
        sections = content.get("sections", [])
        if not sections:
            # Build SOUL.md from flat keys
            lines = ["# Soul", ""]
            for key, value in content.items():
                heading = key.replace("_", " ").title()
                lines.append(f"## {heading}")
                if isinstance(value, list):
                    for item in value:
                        lines.append(f"- {item}")
                elif isinstance(value, str):
                    lines.append(value)
                else:
                    lines.append(str(value))
                lines.append("")
            soul_md = "\n".join(lines)
        else:
            lines = []
            for s in sections:
                lines.append(f"## {s.get('id', '').replace('_', ' ').title()}")
                lines.append(s.get("content", ""))
                lines.append("")
            soul_md = "\n".join(lines)

        # Verify SOUL.md is usable
        assert "## Identity" in soul_md
        assert "Scout" in soul_md
        assert "## Voice" in soul_md
        assert "## Slack Id" in soul_md
