#!/usr/bin/env python3
"""Script to seed initial persona prompts."""

import sys
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from prompt_forge.db.persona_store import get_persona_store


def main():
    """Seed initial persona prompts."""
    print("Seeding initial persona prompts...")

    store = get_persona_store()
    store.seed_initial_personas()

    print("✅ Initial persona prompts seeded successfully!")
    print("Available personas: researcher, developer, reviewer, tester, architect")


if __name__ == "__main__":
    main()
