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
        parent_slug: str | None = None,
    ) -> dict[str, Any]:
        """Create a new prompt. Optionally creates an initial version."""
        # Check for duplicate slug
        existing = self.db.select("prompts", filters={"slug": slug})
        if existing:
            raise ValueError(f"Prompt with slug '{slug}' already exists")

        # Validate parent exists if specified
        if parent_slug:
            parent = self.db.select("prompts", filters={"slug": parent_slug})
            if not parent:
                raise ValueError(f"Parent prompt '{parent_slug}' not found")

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
                "parent_slug": parent_slug,
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
                    "override_sections": {},
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
                r
                for r in results
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

    def get_prompt_chain(self, slug: str) -> list[dict[str, Any]]:
        """Return the full inheritance chain (child → parent → grandparent).

        Raises ValueError on circular inheritance.
        """
        chain: list[dict[str, Any]] = []
        seen: set[str] = set()
        current_slug: str | None = slug

        while current_slug:
            if current_slug in seen:
                raise ValueError(
                    f"Circular inheritance detected: {' → '.join(s['slug'] for s in chain)} → {current_slug}"
                )
            seen.add(current_slug)

            prompt = self.get_prompt(current_slug)
            if not prompt:
                raise ValueError(f"Prompt '{current_slug}' not found in inheritance chain")

            chain.append(prompt)
            current_slug = prompt.get("parent_slug")

        return chain

    def get_effective_content(
        self,
        slug: str,
        branch: str = "main",
        version: int | None = None,
    ) -> dict[str, Any]:
        """Resolve inheritance by merging parent content with child overrides.

        Child sections override parent; parent sections not in child are inherited.
        """
        chain = self.get_prompt_chain(slug)

        # Resolve content for each prompt in the chain
        from prompt_forge.core.vcs import VersionControl

        vcs = VersionControl(self.db)

        # Build merged content starting from the root ancestor
        merged_sections: dict[str, dict[str, Any]] = {}
        merged_variables: dict[str, Any] = {}
        merged_metadata: dict[str, Any] = {}

        # Process from root (last) to child (first)
        for prompt in reversed(chain):
            prompt_id = str(prompt["id"])

            if version is not None and prompt["slug"] == slug:
                ver = vcs.get_version(prompt_id, version, branch)
            else:
                # Get latest version
                history = vcs.history(prompt_id, branch, limit=1)
                ver = history[0] if history else None

            if not ver:
                continue

            content = ver["content"]
            for section in content.get("sections", []):
                merged_sections[section["id"]] = section
            merged_variables.update(content.get("variables", {}))
            merged_metadata.update(content.get("metadata", {}))

        return {
            "sections": list(merged_sections.values()),
            "variables": merged_variables,
            "metadata": merged_metadata,
        }


@lru_cache
def get_registry() -> PromptRegistry:
    """Get cached registry instance."""
    return PromptRegistry(get_supabase_client())
