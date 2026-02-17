"""NATS subscriber for refinement proposals.

Listens to:
- pattern.refinement.proposed — creates refinement branches with proposed changes
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()

_nats_available = False
try:
    import nats as nats_lib

    _nats_available = True
except ImportError:
    pass


class RefinementConsumer:
    """Subscribes to NATS refinement events and creates refinement branches."""

    def __init__(self, nats_url: str = "nats://localhost:4222") -> None:
        self.nats_url = nats_url
        self._nc = None
        self._subs = []
        self._connected = False

    async def connect(self) -> bool:
        """Connect to NATS. Returns True if successful."""
        if not _nats_available:
            logger.info("refinement_consumer.nats_not_installed")
            return False
        try:
            self._nc = await nats_lib.connect(self.nats_url)
            self._connected = True
            logger.info("refinement_consumer.connected", url=self.nats_url)
            return True
        except Exception as e:
            logger.warning("refinement_consumer.connect_failed", error=str(e))
            return False

    async def start(self) -> None:
        """Start consuming refinement events."""
        if not self._connected:
            return

        sub = await self._nc.subscribe(
            "pattern.refinement.proposed", cb=self._handle_refinement_proposed
        )
        self._subs = [sub]
        logger.info(
            "refinement_consumer.started",
            subjects=["pattern.refinement.proposed"],
        )

    async def stop(self) -> None:
        """Stop consuming and disconnect."""
        for sub in self._subs:
            try:
                await sub.unsubscribe()
            except Exception:
                pass
        if self._nc and self._connected:
            try:
                await self._nc.close()
            except Exception:
                pass
        self._connected = False
        logger.info("refinement_consumer.stopped")

    async def _handle_refinement_proposed(self, msg) -> None:
        """Handle pattern.refinement.proposed event.

        Expected event data:
        {
          "target_slug": "kai-soul",
          "section": "reasoning",
          "proposed_change": "Updated reasoning instructions...",
          "source_patterns": ["dredd-pattern-1", "dredd-pattern-2"]
        }
        """
        try:
            payload = json.loads(msg.data.decode())
            data = payload.get("data", payload)

            target_slug = data.get("target_slug")
            section = data.get("section")
            proposed_change = data.get("proposed_change")
            source_patterns = data.get("source_patterns", [])

            if not target_slug or not section or not proposed_change:
                logger.warning("refinement_consumer.incomplete_event", data=data)
                return

            await self._create_refinement_branch(
                target_slug, section, proposed_change, source_patterns, payload
            )

        except Exception as e:
            logger.warning("refinement_consumer.handle_error", error=str(e))

    async def _create_refinement_branch(
        self,
        target_slug: str,
        section: str,
        proposed_change: str,
        source_patterns: list[str],
        event_payload: dict,
    ) -> None:
        """Create a refinement branch with the proposed change."""
        try:
            from prompt_forge.core.registry import get_registry
            from prompt_forge.core.vcs import get_vcs

            registry = get_registry()
            vcs = get_vcs()

            # 1. Look up the target prompt by slug
            prompt = registry.get_prompt(target_slug)
            if not prompt:
                logger.warning("refinement_consumer.prompt_not_found", slug=target_slug)
                return

            prompt_id = str(prompt["id"])

            # 2. Get latest version to base the change on
            latest_versions = vcs.history(prompt_id, "main", limit=1)
            latest_version = latest_versions[0] if latest_versions else None
            if not latest_version:
                logger.warning("refinement_consumer.no_versions", slug=target_slug)
                return

            # 3. Create branch name with timestamp
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            branch_name = f"refinement/{section}/{timestamp}"

            # 4. Create the branch from latest version
            branch = vcs.create_branch(
                prompt_id=prompt_id, branch_name=branch_name, from_branch="main"
            )

            # 5. Apply the proposed change to the target section
            current_content = latest_version["content"]
            updated_content = self._apply_section_change(current_content, section, proposed_change)

            # 6. Create new version on the branch with the change
            commit_message = f"Refinement proposal for {section} section"
            if source_patterns:
                commit_message += f" (from: {', '.join(source_patterns)})"

            vcs.commit(
                prompt_id=prompt_id,
                content=updated_content,
                message=commit_message,
                author="refinement-system",
                branch=branch_name,
            )

            # 7. Store metadata about the proposal
            await self._store_proposal_metadata(branch["id"], source_patterns, event_payload)

            logger.info(
                "refinement_consumer.branch_created",
                slug=target_slug,
                branch=branch_name,
                section=section,
                patterns=source_patterns,
            )

        except Exception as e:
            logger.warning(
                "refinement_consumer.create_branch_error",
                slug=target_slug,
                section=section,
                error=str(e),
            )

    def _apply_section_change(self, content: dict, section_name: str, proposed_change: str) -> dict:
        """Apply the proposed change to the specified section."""
        updated_content = dict(content)
        sections = updated_content.get("sections", [])

        # Find and update the target section
        updated_sections = []
        section_found = False

        for section in sections:
            if section.get("id") == section_name or section.get("name") == section_name:
                # Update this section with the proposed change
                updated_section = dict(section)
                updated_section["content"] = proposed_change
                updated_sections.append(updated_section)
                section_found = True
            else:
                updated_sections.append(section)

        # If section doesn't exist, create it
        if not section_found:
            new_section = {
                "id": section_name,
                "name": section_name.replace("_", " ").title(),
                "content": proposed_change,
            }
            updated_sections.append(new_section)

        updated_content["sections"] = updated_sections
        return updated_content

    async def _store_proposal_metadata(
        self, branch_id: str, source_patterns: list[str], event_payload: dict
    ) -> None:
        """Store metadata about the refinement proposal."""
        try:
            from prompt_forge.db.client import get_supabase_client

            db = get_supabase_client()

            # Store in a refinement_proposals table (if it exists)
            # This is optional - the briefing doesn't require a specific table
            metadata = {
                "branch_id": branch_id,
                "source_patterns": source_patterns,
                "event_payload": event_payload,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            # Try to store, but don't fail if table doesn't exist
            try:
                db.insert("refinement_proposals", metadata)
            except Exception:
                # Table might not exist, which is fine
                pass

        except Exception as e:
            logger.debug("refinement_consumer.metadata_store_error", error=str(e))


_consumer: RefinementConsumer | None = None


def get_refinement_consumer() -> RefinementConsumer:
    """Get the global refinement consumer (lazy init)."""
    global _consumer
    if _consumer is None:
        nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
        _consumer = RefinementConsumer(nats_url)
    return _consumer
