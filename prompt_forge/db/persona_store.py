"""Store layer for persona prompt operations."""

from __future__ import annotations


import structlog

from prompt_forge.db.client import SupabaseClient, get_supabase_client
from prompt_forge.db.models import PersonaPromptRow

logger = structlog.get_logger()


class PersonaPromptStore:
    """Store operations for persona prompts."""

    def __init__(self, db: SupabaseClient) -> None:
        self.db = db

    def get_latest_persona_prompt(self, persona: str) -> PersonaPromptRow | None:
        """Get the latest version of a persona prompt."""
        rows = self.db.select(
            "persona_prompts",
            filters={"persona": persona, "is_latest": True},
            limit=1,
        )
        if not rows:
            return None
        return PersonaPromptRow(**rows[0])

    def get_persona_prompt_version(self, persona: str, version: int) -> PersonaPromptRow | None:
        """Get a specific version of a persona prompt."""
        rows = self.db.select(
            "persona_prompts",
            filters={"persona": persona, "version": version},
            limit=1,
        )
        if not rows:
            return None
        return PersonaPromptRow(**rows[0])

    def create_persona_prompt_version(self, persona: str, template: str) -> PersonaPromptRow:
        """Create a new version of a persona prompt."""
        # Get the next version number
        existing_rows = self.db.select(
            "persona_prompts",
            filters={"persona": persona},
            order_by="version",
            ascending=False,
            limit=1,
        )
        next_version = 1 if not existing_rows else existing_rows[0]["version"] + 1

        # Mark all existing versions as not latest
        if existing_rows:
            # Update all existing versions to not be latest
            query = (
                self.db.client.table("persona_prompts")
                .update({"is_latest": False})
                .eq("persona", persona)
            )
            query.execute()

        # Create the new version
        data = {
            "persona": persona,
            "version": next_version,
            "template": template,
            "is_latest": True,
        }

        row_data = self.db.insert("persona_prompts", data)
        logger.info(
            "persona_prompt.created",
            persona=persona,
            version=next_version,
            id=row_data["id"],
        )

        return PersonaPromptRow(**row_data)

    def list_persona_versions(self, persona: str) -> list[PersonaPromptRow]:
        """List all versions of a persona prompt."""
        rows = self.db.select(
            "persona_prompts",
            filters={"persona": persona},
            order_by="version",
            ascending=False,
        )
        return [PersonaPromptRow(**row) for row in rows]

    def seed_initial_personas(self) -> None:
        """Seed initial personas with basic templates."""
        initial_personas = {
            "researcher": """You are a Researcher persona with expertise in information gathering and analysis.

Your objective: {{objective}}

Context: {{context}}

Constraints: {{constraints}}

Scope paths: {{scope_paths}}

Alexandria context: {{alexandria_context}}

Focus on thorough research, fact-checking, and providing comprehensive information with proper citations and sources.""",
            "developer": """You are a Developer persona with expertise in software engineering and coding.

Your objective: {{objective}}

Context: {{context}}

Constraints: {{constraints}}

Scope paths: {{scope_paths}}

Alexandria context: {{alexandria_context}}

Focus on clean, efficient code, best practices, testing, and maintainable solutions. Provide working code examples and explanations.""",
            "reviewer": """You are a Reviewer persona with expertise in code review and quality assurance.

Your objective: {{objective}}

Context: {{context}}

Constraints: {{constraints}}

Scope paths: {{scope_paths}}

Alexandria context: {{alexandria_context}}

Focus on thorough code review, identifying issues, suggesting improvements, and ensuring quality standards are met.""",
            "tester": """You are a Tester persona with expertise in testing strategies and quality assurance.

Your objective: {{objective}}

Context: {{context}}

Constraints: {{constraints}}

Scope paths: {{scope_paths}}

Alexandria context: {{alexandria_context}}

Focus on comprehensive testing strategies, test case design, bug identification, and ensuring software quality through rigorous testing.""",
            "architect": """You are an Architect persona with expertise in system design and technical architecture.

Your objective: {{objective}}

Context: {{context}}

Constraints: {{constraints}}

Scope paths: {{scope_paths}}

Alexandria context: {{alexandria_context}}

Focus on high-level system design, scalability, performance, security considerations, and architectural best practices.""",
        }

        for persona, template in initial_personas.items():
            # Check if persona already exists
            existing = self.get_latest_persona_prompt(persona)
            if existing:
                logger.info("persona_prompt.seed_skip", persona=persona, reason="already_exists")
                continue

            # Create initial version
            self.create_persona_prompt_version(persona, template)
            logger.info("persona_prompt.seeded", persona=persona)


def get_persona_store() -> PersonaPromptStore:
    """Get PersonaPromptStore instance."""
    return PersonaPromptStore(get_supabase_client())
