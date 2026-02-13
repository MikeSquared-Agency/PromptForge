"""Composition Engine — assembles agent identities from prompt components."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import structlog

from prompt_forge.core.registry import PromptRegistry
from prompt_forge.core.resolver import PromptResolver, get_resolver

logger = structlog.get_logger()


class CompositionEngine:
    """Composes agent prompts from reusable components."""

    def __init__(self, resolver: PromptResolver, registry: PromptRegistry | None = None) -> None:
        self.resolver = resolver
        self.registry = registry

    def compose(
        self,
        persona_slug: str,
        skill_slugs: list[str] | None = None,
        constraint_slugs: list[str] | None = None,
        variables: dict[str, str] | None = None,
        branch: str = "main",
        strategy: str = "latest",
    ) -> dict[str, Any]:
        """Compose an agent prompt from components.

        Resolves each component, assembles into a final prompt, and returns
        the composed text with a provenance manifest.
        """
        skill_slugs = skill_slugs or []
        constraint_slugs = constraint_slugs or []
        variables = variables or {}
        warnings: list[str] = []

        components: list[dict[str, Any]] = []
        sections: list[str] = []

        # Resolve persona (with inheritance if registry available)
        persona_version = self.resolver.resolve(slug=persona_slug, branch=branch, strategy=strategy)
        components.append(
            {
                "slug": persona_slug,
                "type": "persona",
                "version": persona_version["version"],
                "branch": branch,
            }
        )
        if self.registry:
            effective = self.registry.get_effective_content(persona_slug, branch)
            sections.append(self._extract_text(effective, "persona"))
        else:
            sections.append(self._extract_text(persona_version["content"], "persona"))

        # Resolve skills
        for slug in skill_slugs:
            try:
                version = self.resolver.resolve(slug=slug, branch=branch, strategy=strategy)
                components.append(
                    {
                        "slug": slug,
                        "type": "skill",
                        "version": version["version"],
                        "branch": branch,
                    }
                )
                if self.registry:
                    effective = self.registry.get_effective_content(slug, branch)
                    sections.append(self._extract_text(effective, "skill"))
                else:
                    sections.append(self._extract_text(version["content"], "skill"))
            except Exception as e:
                warnings.append(f"Failed to resolve skill '{slug}': {e}")

        # Resolve constraints
        for slug in constraint_slugs:
            try:
                version = self.resolver.resolve(slug=slug, branch=branch, strategy=strategy)
                components.append(
                    {
                        "slug": slug,
                        "type": "constraint",
                        "version": version["version"],
                        "branch": branch,
                    }
                )
                if self.registry:
                    effective = self.registry.get_effective_content(slug, branch)
                    sections.append(self._extract_text(effective, "constraint"))
                else:
                    sections.append(self._extract_text(version["content"], "constraint"))
            except Exception as e:
                warnings.append(f"Failed to resolve constraint '{slug}': {e}")

        # Assemble prompt
        prompt_text = "\n\n".join(sections)

        # Apply variable substitution
        prompt_text = self._apply_variables(prompt_text, variables)

        # Check for unresolved variables
        unresolved = re.findall(r"\{\{(\w+)\}\}", prompt_text)
        if unresolved:
            warnings.append(f"Unresolved variables: {', '.join(unresolved)}")

        # Detect conflicts
        warnings.extend(self._detect_conflicts(sections))

        # Estimate tokens (rough: 1 token ≈ 4 chars)
        estimated_tokens = len(prompt_text) // 4

        manifest = {
            "composed_at": datetime.now(timezone.utc).isoformat(),
            "components": components,
            "variables_applied": variables,
            "estimated_tokens": estimated_tokens,
        }

        logger.info(
            "compose.assembled",
            persona=persona_slug,
            skills=skill_slugs,
            constraints=constraint_slugs,
            tokens=estimated_tokens,
        )

        return {
            "prompt": prompt_text,
            "manifest": manifest,
            "warnings": warnings,
        }

    def _extract_text(self, content: dict[str, Any], component_type: str) -> str:
        """Extract readable text from structured prompt content."""
        sections = content.get("sections", [])
        if sections:
            return "\n\n".join(s.get("content", "") for s in sections)
        # Fallback: if content is flat text
        if "text" in content:
            return content["text"]
        return str(content)

    def _apply_variables(self, text: str, variables: dict[str, str]) -> str:
        """Replace {{variable}} placeholders with values."""
        for key, value in variables.items():
            text = text.replace(f"{{{{{key}}}}}", value)
        return text

    def _detect_conflicts(self, sections: list[str]) -> list[str]:
        """Detect potential conflicts between composed sections."""
        warnings: list[str] = []

        # Check for contradictory output format instructions
        format_keywords = ["json", "markdown", "plain text", "xml", "yaml"]
        found_formats: list[str] = []
        for section in sections:
            lower = section.lower()
            for fmt in format_keywords:
                if f"respond in {fmt}" in lower or f"output in {fmt}" in lower:
                    found_formats.append(fmt)

        if len(set(found_formats)) > 1:
            warnings.append(f"Conflicting output formats detected: {', '.join(set(found_formats))}")

        return warnings


@lru_cache
def get_composer() -> CompositionEngine:
    """Get cached composer instance."""
    from prompt_forge.core.registry import get_registry

    return CompositionEngine(get_resolver(), get_registry())
