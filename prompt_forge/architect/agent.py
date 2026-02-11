"""PromptArchitect — AI agent for prompt design, refinement, and evaluation.

The PromptArchitect runs as an OpenClaw agent with direct access to
PromptForge core functions (no HTTP round-trip).
"""

from __future__ import annotations

from typing import Any

import structlog

from prompt_forge.architect.prompts import ARCHITECT_SYSTEM_PROMPT
from prompt_forge.architect.tools import get_tool_declarations
from prompt_forge.core.composer import CompositionEngine
from prompt_forge.core.registry import PromptRegistry
from prompt_forge.core.vcs import VersionControl

logger = structlog.get_logger()


class PromptArchitect:
    """The PromptArchitect agent — designs, refines, composes, and evaluates prompts.

    Modes:
    - design: Create new prompts from requirements
    - refine: Improve existing prompts based on feedback/metrics
    - compose: Build and validate compositions
    - evaluate: Analyse performance and suggest improvements
    """

    def __init__(
        self,
        registry: PromptRegistry,
        vcs: VersionControl,
        composer: CompositionEngine,
    ) -> None:
        self.registry = registry
        self.vcs = vcs
        self.composer = composer
        self.system_prompt = ARCHITECT_SYSTEM_PROMPT
        self.tools = get_tool_declarations()

    def design(self, requirements: str, prompt_type: str = "persona") -> dict[str, Any]:
        """Design a new prompt from natural language requirements.

        TODO Phase 2: Use Anthropic API for AI-assisted design.
        For now, returns a structured template.
        """
        logger.info("architect.design", type=prompt_type)
        return {
            "mode": "design",
            "type": prompt_type,
            "requirements": requirements,
            "template": {
                "sections": [
                    {"id": "identity", "label": "Identity", "content": ""},
                    {"id": "skills", "label": "Skills", "content": ""},
                    {"id": "constraints", "label": "Constraints", "content": ""},
                    {"id": "output_format", "label": "Output Format", "content": ""},
                ],
                "variables": {},
                "metadata": {"target_model": "claude-sonnet-4-20250514"},
            },
            "status": "draft",
        }

    def refine(self, slug: str, feedback: str) -> dict[str, Any]:
        """Refine an existing prompt based on feedback.

        TODO Phase 2: AI-assisted refinement with usage metrics.
        """
        prompt = self.registry.get_prompt(slug)
        if not prompt:
            raise ValueError(f"Prompt '{slug}' not found")

        logger.info("architect.refine", slug=slug)
        return {
            "mode": "refine",
            "slug": slug,
            "feedback": feedback,
            "status": "pending_implementation",
        }

    def evaluate(self, slug: str) -> dict[str, Any]:
        """Evaluate a prompt's performance.

        TODO Phase 2: Aggregate usage metrics and provide analysis.
        """
        prompt = self.registry.get_prompt(slug)
        if not prompt:
            raise ValueError(f"Prompt '{slug}' not found")

        logger.info("architect.evaluate", slug=slug)
        return {
            "mode": "evaluate",
            "slug": slug,
            "status": "pending_implementation",
        }
