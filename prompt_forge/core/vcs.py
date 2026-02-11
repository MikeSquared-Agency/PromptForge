"""Version Control System — commit, history, rollback for prompts."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import structlog

from prompt_forge.db.client import SupabaseClient, get_supabase_client

logger = structlog.get_logger()


class VersionControl:
    """Git-like version control for prompt content."""

    def __init__(self, db: SupabaseClient) -> None:
        self.db = db

    def commit(
        self,
        prompt_id: str,
        content: dict[str, Any],
        message: str = "Update",
        author: str = "system",
        branch: str = "main",
    ) -> dict[str, Any]:
        """Create a new version (commit) of a prompt."""
        # Get current head for this prompt+branch
        history = self.db.select(
            "prompt_versions",
            filters={"prompt_id": prompt_id, "branch": branch},
            order_by="version",
            ascending=False,
            limit=1,
        )

        next_version = 1
        parent_id = None
        if history:
            next_version = history[0]["version"] + 1
            parent_id = history[0]["id"]

        version = self.db.insert(
            "prompt_versions",
            {
                "prompt_id": prompt_id,
                "version": next_version,
                "content": content,
                "message": message,
                "author": author,
                "parent_version_id": parent_id,
                "branch": branch,
            },
        )

        logger.info(
            "vcs.commit",
            prompt_id=prompt_id,
            version=next_version,
            branch=branch,
            author=author,
        )
        return version

    def history(
        self,
        prompt_id: str,
        branch: str = "main",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get version history for a prompt on a branch."""
        return self.db.select(
            "prompt_versions",
            filters={"prompt_id": prompt_id, "branch": branch},
            order_by="version",
            ascending=False,
            limit=limit,
        )

    def get_version(
        self,
        prompt_id: str,
        version: int,
        branch: str = "main",
    ) -> dict[str, Any] | None:
        """Get a specific version."""
        results = self.db.select(
            "prompt_versions",
            filters={"prompt_id": prompt_id, "version": version, "branch": branch},
        )
        return results[0] if results else None

    def rollback(
        self,
        prompt_id: str,
        version: int,
        author: str = "system",
        branch: str = "main",
    ) -> dict[str, Any] | None:
        """Rollback to a previous version by creating a new commit with that content."""
        target = self.get_version(prompt_id, version, branch)
        if not target:
            return None

        return self.commit(
            prompt_id=prompt_id,
            content=target["content"],
            message=f"Rollback to version {version}",
            author=author,
            branch=branch,
        )

    # TODO Phase 2: create_branch, merge_branch, tag support


@lru_cache
def get_vcs() -> VersionControl:
    """Get cached VCS instance."""
    return VersionControl(get_supabase_client())
