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

        Queries usage_log for version with highest success rate (minimum 3 uses).
        Falls back to latest if no usage data.
        """
        # Get all versions on this branch
        versions = self.db.select(
            "prompt_versions",
            filters={"prompt_id": prompt_id, "branch": branch},
        )
        if not versions:
            raise ValueError(f"No versions found for prompt on branch '{branch}'")

        # Get all usage logs for this prompt
        logs = self.db.select(
            "prompt_usage_log",
            filters={"prompt_id": prompt_id},
        )

        if not logs:
            logger.info("resolver.best_performing_no_data", prompt_id=prompt_id)
            return self._resolve_latest(prompt_id, branch)

        # Build version_id set for this branch
        branch_version_ids = {v["id"] for v in versions}

        # Calculate success rate per version
        version_stats: dict[str, dict[str, int]] = {}
        for log in logs:
            vid = log.get("version_id")
            if vid not in branch_version_ids:
                continue
            if vid not in version_stats:
                version_stats[vid] = {"total": 0, "success": 0}
            version_stats[vid]["total"] += 1
            if log.get("outcome") == "success":
                version_stats[vid]["success"] += 1

        # Filter to versions with minimum usage threshold
        min_uses = 3
        candidates = {
            vid: stats["success"] / stats["total"]
            for vid, stats in version_stats.items()
            if stats["total"] >= min_uses
        }

        if not candidates:
            logger.info("resolver.best_performing_insufficient_data", prompt_id=prompt_id)
            return self._resolve_latest(prompt_id, branch)

        # Pick highest success rate
        best_vid = max(candidates, key=candidates.get)  # type: ignore
        best_version = [v for v in versions if v["id"] == best_vid]
        if best_version:
            logger.info(
                "resolver.best_performing_resolved",
                prompt_id=prompt_id,
                version_id=best_vid,
                success_rate=candidates[best_vid],
            )
            return best_version[0]

        return self._resolve_latest(prompt_id, branch)


@lru_cache
def get_resolver() -> PromptResolver:
    """Get cached resolver instance."""
    return PromptResolver(get_supabase_client())
