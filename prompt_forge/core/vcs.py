"""Version Control System — commit, history, rollback for prompts."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import structlog

from prompt_forge.core.scanner import PromptScanner
from prompt_forge.db.client import SupabaseClient, get_supabase_client

logger = structlog.get_logger()


class VersionControl:
    """Git-like version control for prompt content."""

    def __init__(self, db: SupabaseClient) -> None:
        self.db = db
        self.scanner = PromptScanner()

    def commit(
        self,
        prompt_id: str,
        content: dict[str, Any],
        message: str = "Update",
        author: str = "system",
        branch: str = "main",
    ) -> dict[str, Any]:
        """Create a new version (commit) of a prompt.

        Scans content for injection attempts before committing.
        Critical findings will raise an error. Medium/high findings
        are included as warnings in the response.
        """
        # Scan for injection attempts
        scan_result = self.scanner.scan(content)
        if scan_result.risk_level == "critical":
            finding_details = "; ".join(
                f"{f.pattern_name}: {f.description}" for f in scan_result.findings
            )
            raise ValueError(f"Critical injection findings detected: {finding_details}")
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

        # Attach scan warnings if any
        if scan_result.findings:
            version["scan_warnings"] = [
                {"pattern": f.pattern_name, "severity": f.severity, "description": f.description}
                for f in scan_result.findings
            ]

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

    def create_branch(
        self,
        prompt_id: str,
        branch_name: str,
        from_branch: str = "main",
    ) -> dict[str, Any]:
        """Create a new branch from an existing branch's head."""
        # Check branch doesn't already exist
        existing = self.db.select(
            "prompt_branches",
            filters={"prompt_id": prompt_id, "name": branch_name},
        )
        if existing:
            raise ValueError(f"Branch '{branch_name}' already exists for this prompt")

        # Get head of source branch
        head = self.db.select(
            "prompt_versions",
            filters={"prompt_id": prompt_id, "branch": from_branch},
            order_by="version",
            ascending=False,
            limit=1,
        )
        if not head:
            raise ValueError(f"No versions found on branch '{from_branch}'")

        head_version = head[0]

        # Create branch record
        branch = self.db.insert(
            "prompt_branches",
            {
                "prompt_id": prompt_id,
                "name": branch_name,
                "head_version_id": head_version["id"],
                "base_version_id": head_version["id"],
                "status": "active",
            },
        )

        # Copy head content as first version on new branch
        self.commit(
            prompt_id=prompt_id,
            content=head_version["content"],
            message=f"Branch '{branch_name}' from '{from_branch}' v{head_version['version']}",
            author="system",
            branch=branch_name,
        )

        logger.info(
            "vcs.branch_created",
            prompt_id=prompt_id,
            branch=branch_name,
            from_branch=from_branch,
        )
        return branch

    def list_branches(self, prompt_id: str) -> list[dict[str, Any]]:
        """List all branches for a prompt."""
        return self.db.select(
            "prompt_branches",
            filters={"prompt_id": prompt_id},
        )

    def merge_branch(
        self,
        prompt_id: str,
        source_branch: str,
        target_branch: str = "main",
        strategy: str = "theirs",
        author: str = "system",
    ) -> dict[str, Any]:
        """Merge source branch into target branch.

        Strategies:
        - ours: Keep target branch content for conflicts
        - theirs: Keep source branch content for conflicts
        - section_merge: Merge non-conflicting sections, source wins on conflicts
        """
        from prompt_forge.core.differ import StructuralDiffer

        # Get heads of both branches
        source_head = self.db.select(
            "prompt_versions",
            filters={"prompt_id": prompt_id, "branch": source_branch},
            order_by="version",
            ascending=False,
            limit=1,
        )
        target_head = self.db.select(
            "prompt_versions",
            filters={"prompt_id": prompt_id, "branch": target_branch},
            order_by="version",
            ascending=False,
            limit=1,
        )

        if not source_head:
            raise ValueError(f"No versions on source branch '{source_branch}'")
        if not target_head:
            raise ValueError(f"No versions on target branch '{target_branch}'")

        source_content = source_head[0]["content"]
        target_content = target_head[0]["content"]

        if strategy == "ours":
            merged_content = target_content
        elif strategy == "theirs":
            merged_content = source_content
        elif strategy == "section_merge":
            merged_content = self._section_merge(target_content, source_content)
        else:
            raise ValueError(f"Unknown merge strategy: {strategy}")

        # Commit merged content to target branch
        version = self.commit(
            prompt_id=prompt_id,
            content=merged_content,
            message=f"Merge '{source_branch}' into '{target_branch}' ({strategy})",
            author=author,
            branch=target_branch,
        )

        # Update branch status
        branches = self.db.select(
            "prompt_branches",
            filters={"prompt_id": prompt_id, "name": source_branch},
        )
        if branches:
            self.db.update("prompt_branches", branches[0]["id"], {"status": "merged"})

        logger.info(
            "vcs.branch_merged",
            prompt_id=prompt_id,
            source=source_branch,
            target=target_branch,
            strategy=strategy,
        )
        return version

    def _section_merge(
        self,
        target_content: dict[str, Any],
        source_content: dict[str, Any],
    ) -> dict[str, Any]:
        """Section-level merge: target is base, source sections override on conflict."""
        target_sections = {s["id"]: s for s in target_content.get("sections", [])}
        source_sections = {s["id"]: s for s in source_content.get("sections", [])}

        # Start with target, overlay source
        merged_sections = dict(target_sections)
        for sid, section in source_sections.items():
            merged_sections[sid] = section

        # Merge variables and metadata
        merged_vars = {**target_content.get("variables", {}), **source_content.get("variables", {})}
        merged_meta = {**target_content.get("metadata", {}), **source_content.get("metadata", {})}

        return {
            "sections": list(merged_sections.values()),
            "variables": merged_vars,
            "metadata": merged_meta,
        }


@lru_cache
def get_vcs() -> VersionControl:
    """Get cached VCS instance."""
    return VersionControl(get_supabase_client())
