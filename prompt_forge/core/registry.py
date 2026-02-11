"""Prompt Registry — CRUD operations for prompt management."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import structlog

from prompt_forge.db.client import SupabaseClient, get_supabase_client

logger = structlog.get_logger()


class PromptRegistry:
    """Manages prompt lifecycle — create, read, update, archive."""

    def __init__(self, db: SupabaseClient) -> None:
        self.db = db

    def create_prompt(
        self,
        slug: str,
        name: str,
        type: str,
        description: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        content: dict[str, Any] | None = None,
        initial_message: str = "Initial version",
    ) -> dict[str, Any]:
        """Create a new prompt. Optionally creates an initial version."""
        # Check for duplicate slug
        existing = self.db.select("prompts", filters={"slug": slug})
        if existing:
            raise ValueError(f"Prompt with slug '{slug}' already exists")

        prompt = self.db.insert(
            "prompts",
            {
                "slug": slug,
                "name": name,
                "type": type,
                "description": description,
                "tags": tags or [],
                "metadata": metadata or {},
                "archived": False,
            },
        )

        # Create initial version if content provided
        if content is not None:
            self.db.insert(
                "prompt_versions",
                {
                    "prompt_id": prompt["id"],
                    "version": 1,
                    "content": content,
                    "message": initial_message,
                    "author": "system",
                    "branch": "main",
                },
            )

        logger.info("prompt.created", slug=slug, type=type)
        return prompt

    def get_prompt(self, slug: str) -> dict[str, Any] | None:
        """Get a prompt by slug."""
        results = self.db.select("prompts", filters={"slug": slug})
        return results[0] if results else None

    def list_prompts(
        self,
        type: str | None = None,
        tag: str | None = None,
        search: str | None = None,
        archived: bool = False,
    ) -> list[dict[str, Any]]:
        """List prompts with optional filters."""
        filters: dict[str, Any] = {"archived": archived}
        if type:
            filters["type"] = type

        results = self.db.select("prompts", filters=filters)

        # Client-side filtering for tags and search (Supabase array contains)
        if tag:
            results = [r for r in results if tag in r.get("tags", [])]
        if search:
            search_lower = search.lower()
            results = [
                r for r in results
                if search_lower in r.get("name", "").lower()
                or search_lower in r.get("description", "").lower()
                or search_lower in r.get("slug", "").lower()
            ]

        return results

    def update_prompt(self, slug: str, **kwargs: Any) -> dict[str, Any] | None:
        """Update a prompt's metadata."""
        prompt = self.get_prompt(slug)
        if not prompt:
            return None

        updated = self.db.update("prompts", prompt["id"], kwargs)
        logger.info("prompt.updated", slug=slug, fields=list(kwargs.keys()))
        return updated

    def archive_prompt(self, slug: str) -> bool:
        """Soft-delete a prompt by setting archived=True."""
        prompt = self.get_prompt(slug)
        if not prompt:
            return False

        self.db.update("prompts", prompt["id"], {"archived": True})
        logger.info("prompt.archived", slug=slug)
        return True


@lru_cache
def get_registry() -> PromptRegistry:
    """Get cached registry instance."""
    return PromptRegistry(get_supabase_client())
