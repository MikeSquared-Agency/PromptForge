"""Smart Resolution — selects the right prompt version based on strategy."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import structlog

from prompt_forge.db.client import SupabaseClient, get_supabase_client

logger = structlog.get_logger()


class PromptResolver:
    """Resolves prompt slugs to specific versions using configurable strategies."""

    def __init__(self, db: SupabaseClient) -> None:
        self.db = db

    def resolve(
        self,
        slug: str,
        branch: str = "main",
        version: int | None = None,
        strategy: str = "latest",
    ) -> dict[str, Any]:
        """Resolve a prompt slug to a specific version.

        Strategies:
        - latest: Most recent version on the branch
        - pinned: Exact version number (requires version param)
        - best_performing: Version with highest success rate (Phase 2)
        """
        # Look up prompt
        prompts = self.db.select("prompts", filters={"slug": slug, "archived": False})
        if not prompts:
            raise ValueError(f"Prompt '{slug}' not found or archived")

        prompt_id = prompts[0]["id"]

        if strategy == "pinned":
            if version is None:
                raise ValueError("Pinned strategy requires a version number")
            return self._resolve_pinned(prompt_id, version, branch)
        elif strategy == "best_performing":
            return self._resolve_best_performing(prompt_id, branch)
        else:  # latest
            return self._resolve_latest(prompt_id, branch)

    def _resolve_latest(self, prompt_id: str, branch: str) -> dict[str, Any]:
        """Get the most recent version on a branch."""
        versions = self.db.select(
            "prompt_versions",
            filters={"prompt_id": prompt_id, "branch": branch},
            order_by="version",
            ascending=False,
            limit=1,
        )
        if not versions:
            raise ValueError(f"No versions found for prompt on branch '{branch}'")
        return versions[0]

    def _resolve_pinned(self, prompt_id: str, version: int, branch: str) -> dict[str, Any]:
        """Get an exact version."""
        versions = self.db.select(
            "prompt_versions",
            filters={"prompt_id": prompt_id, "version": version, "branch": branch},
        )
        if not versions:
            raise ValueError(f"Version {version} not found on branch '{branch}'")
        return versions[0]

    def _resolve_best_performing(self, prompt_id: str, branch: str) -> dict[str, Any]:
        """Resolve to the best-performing version based on usage metrics.

        TODO Phase 2: Implement proper performance-based resolution.
        Falls back to latest for now.
        """
        logger.warning("resolver.best_performing_fallback", prompt_id=prompt_id)
        return self._resolve_latest(prompt_id, branch)


@lru_cache
def get_resolver() -> PromptResolver:
    """Get cached resolver instance."""
    return PromptResolver(get_supabase_client())
