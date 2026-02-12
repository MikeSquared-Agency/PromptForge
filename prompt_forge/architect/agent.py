"""PromptArchitect — AI agent for prompt design, refinement, and evaluation.

The PromptArchitect runs as an OpenClaw agent with direct access to
PromptForge core functions (no HTTP round-trip).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

from prompt_forge.architect.prompts import ARCHITECT_SYSTEM_PROMPT
from prompt_forge.architect.tools import get_tool_declarations
from prompt_forge.core.composer import CompositionEngine
from prompt_forge.core.registry import PromptRegistry
from prompt_forge.core.scanner import PromptScanner
from prompt_forge.core.vcs import VersionControl

logger = structlog.get_logger()

GATEWAY_URL = os.getenv("OPENCLAW_GATEWAY", "http://localhost:18789")


@dataclass
class EvaluationReport:
    """Report from prompt evaluation."""
    slug: str
    structure_score: float  # 0-1
    coverage_score: float  # 0-1
    injection_risk: str  # low/medium/high/critical
    suggestions: list[str] = field(default_factory=list)
    usage_summary: dict[str, Any] = field(default_factory=dict)


class PromptArchitect:
    """The PromptArchitect agent — designs, refines, composes, and evaluates prompts."""

    def __init__(
        self,
        registry: PromptRegistry,
        vcs: VersionControl,
        composer: CompositionEngine,
        gateway_url: str | None = None,
    ) -> None:
        self.registry = registry
        self.vcs = vcs
        self.composer = composer
        self.scanner = PromptScanner()
        self.system_prompt = ARCHITECT_SYSTEM_PROMPT
        self.tools = get_tool_declarations()
        self.gateway_url = gateway_url or GATEWAY_URL

    async def _call_llm(self, user_message: str) -> str:
        """Call the LLM via OpenClaw gateway."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.gateway_url}/v1/chat/completions",
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "messages": [
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                        "max_tokens": 4096,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning("architect.llm_call_failed", error=str(e))
            return ""

    async def design(self, requirements: str, prompt_type: str = "persona") -> dict[str, Any]:
        """Design a new prompt from natural language requirements.

        Uses LLM to generate structured prompt content, then creates it in the registry.
        """
        logger.info("architect.design", type=prompt_type)

        design_prompt = f"""Design a prompt with these requirements:

Type: {prompt_type}
Requirements: {requirements}

Respond with a JSON object containing:
- "slug": a short kebab-case identifier
- "name": a display name
- "description": a brief description
- "content": {{
    "sections": [
      {{"id": "identity", "label": "Identity", "content": "..."}},
      {{"id": "skills", "label": "Skills", "content": "..."}},
      {{"id": "constraints", "label": "Constraints", "content": "..."}},
      {{"id": "output_format", "label": "Output Format", "content": "..."}}
    ],
    "variables": {{}},
    "metadata": {{"estimated_tokens": N, "target_model": "claude-sonnet-4-20250514"}}
  }}

Only output the JSON, no other text."""

        llm_response = await self._call_llm(design_prompt)

        # Try to parse LLM response as JSON
        if llm_response:
            try:
                # Extract JSON from response (handle markdown code blocks)
                json_match = re.search(r'\{[\s\S]*\}', llm_response)
                if json_match:
                    design = json.loads(json_match.group())
                else:
                    design = json.loads(llm_response)
            except (json.JSONDecodeError, ValueError):
                logger.warning("architect.design_parse_failed")
                design = None
        else:
            design = None

        # Fallback to template if LLM fails
        if not design or "content" not in design:
            slug = re.sub(r'[^a-z0-9]+', '-', requirements.lower()[:40]).strip('-')
            if len(slug) < 2:
                slug = "new-prompt"
            design = {
                "slug": slug,
                "name": requirements[:80],
                "description": requirements,
                "content": {
                    "sections": [
                        {"id": "identity", "label": "Identity", "content": f"You are an AI assistant specialised in: {requirements}"},
                        {"id": "skills", "label": "Skills", "content": ""},
                        {"id": "constraints", "label": "Constraints", "content": "Be clear and concise."},
                        {"id": "output_format", "label": "Output Format", "content": ""},
                    ],
                    "variables": {},
                    "metadata": {"estimated_tokens": 100, "target_model": "claude-sonnet-4-20250514"},
                },
            }

        # Create in registry
        try:
            prompt = self.registry.create_prompt(
                slug=design["slug"],
                name=design.get("name", design["slug"]),
                type=prompt_type,
                description=design.get("description", ""),
                content=design["content"],
                initial_message="Designed by PromptArchitect",
            )
            design["prompt"] = prompt
            design["status"] = "created"
        except ValueError as e:
            design["status"] = "draft"
            design["error"] = str(e)

        return design

    async def refine(self, slug: str, feedback: str) -> dict[str, Any]:
        """Refine an existing prompt based on feedback.

        Fetches current version, sends to LLM with feedback, commits improved version.
        """
        prompt = self.registry.get_prompt(slug)
        if not prompt:
            raise ValueError(f"Prompt '{slug}' not found")

        # Get current content
        history = self.vcs.history(str(prompt["id"]), branch="main", limit=1)
        if not history:
            raise ValueError(f"No versions found for '{slug}'")

        current = history[0]
        current_content = current["content"]

        logger.info("architect.refine", slug=slug, current_version=current["version"])

        refine_prompt = f"""Refine this prompt based on the feedback below.

Current content:
{json.dumps(current_content, indent=2)}

Feedback: {feedback}

Return the improved content as a JSON object with the same structure (sections, variables, metadata).
Only output the JSON, no other text."""

        llm_response = await self._call_llm(refine_prompt)

        new_content = None
        if llm_response:
            try:
                json_match = re.search(r'\{[\s\S]*\}', llm_response)
                if json_match:
                    new_content = json.loads(json_match.group())
                else:
                    new_content = json.loads(llm_response)
            except (json.JSONDecodeError, ValueError):
                logger.warning("architect.refine_parse_failed")

        if not new_content or "sections" not in new_content:
            # Apply feedback as a note in constraints if LLM fails
            new_content = dict(current_content)
            sections = list(new_content.get("sections", []))
            for s in sections:
                if s["id"] == "constraints":
                    s["content"] = s.get("content", "") + f"\n\nRefinement feedback: {feedback}"
                    break
            else:
                sections.append({
                    "id": "constraints",
                    "label": "Constraints",
                    "content": f"Refinement feedback: {feedback}",
                })
            new_content["sections"] = sections

        # Commit refined version
        version = self.vcs.commit(
            prompt_id=str(prompt["id"]),
            content=new_content,
            message=f"Refined: {feedback[:100]}",
            author="prompt-architect",
            branch="main",
        )

        return {
            "mode": "refine",
            "slug": slug,
            "version": version,
            "feedback": feedback,
            "status": "committed",
        }

    async def evaluate(self, slug: str) -> EvaluationReport:
        """Evaluate prompt quality — structure, coverage, injection risk."""
        prompt = self.registry.get_prompt(slug)
        if not prompt:
            raise ValueError(f"Prompt '{slug}' not found")

        history = self.vcs.history(str(prompt["id"]), branch="main", limit=1)
        if not history:
            raise ValueError(f"No versions found for '{slug}'")

        content = history[0]["content"]
        suggestions: list[str] = []

        # Structure score: check for expected sections
        expected_sections = {"identity", "skills", "constraints", "output_format"}
        present_sections = {s["id"] for s in content.get("sections", [])}
        structure_score = len(present_sections & expected_sections) / len(expected_sections)

        missing = expected_sections - present_sections
        if missing:
            suggestions.append(f"Missing sections: {', '.join(missing)}")

        # Coverage score: check section content quality
        sections = content.get("sections", [])
        non_empty = sum(1 for s in sections if len(s.get("content", "").strip()) > 10)
        coverage_score = non_empty / max(len(sections), 1)

        for s in sections:
            if len(s.get("content", "").strip()) < 10:
                suggestions.append(f"Section '{s['id']}' has very little content")

        # Injection risk
        scan_result = self.scanner.scan(content)
        injection_risk = scan_result.risk_level

        if scan_result.findings:
            for f in scan_result.findings:
                suggestions.append(f"Injection risk: {f.pattern_name} ({f.severity})")

        # Check variables
        variables = content.get("variables", {})
        if not variables:
            suggestions.append("No template variables defined — consider adding for reusability")

        # Token estimate
        total_text = " ".join(s.get("content", "") for s in sections)
        est_tokens = len(total_text) // 4
        if est_tokens > 2000:
            suggestions.append(f"Prompt is large (~{est_tokens} tokens). Consider trimming.")

        # Usage summary (best-effort)
        usage_summary: dict[str, Any] = {}
        try:
            from prompt_forge.db.client import get_supabase_client
            db = self.registry.db
            logs = db.select("prompt_usage_log", filters={"prompt_id": str(prompt["id"])})
            if logs:
                total = len(logs)
                successes = sum(1 for l in logs if l.get("outcome") == "success")
                usage_summary = {
                    "total_uses": total,
                    "success_rate": round(successes / total, 2) if total else 0,
                }
        except Exception:
            pass

        logger.info("architect.evaluate", slug=slug, structure=structure_score, coverage=coverage_score)

        return EvaluationReport(
            slug=slug,
            structure_score=round(structure_score, 2),
            coverage_score=round(coverage_score, 2),
            injection_risk=injection_risk,
            suggestions=suggestions,
            usage_summary=usage_summary,
        )
