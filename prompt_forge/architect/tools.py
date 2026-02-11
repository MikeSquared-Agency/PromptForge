"""Tool declarations for the PromptArchitect agent.

These follow the OpenClaw tool format and map to core functions.
"""

from __future__ import annotations

from typing import Any


def get_tool_declarations() -> list[dict[str, Any]]:
    """Return tool declarations in OpenClaw format."""
    return [
        {
            "name": "registry.create",
            "description": "Create a new prompt in the registry",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "Unique identifier"},
                    "name": {"type": "string", "description": "Display name"},
                    "type": {"type": "string", "enum": ["persona", "skill", "constraint", "template", "meta"]},
                    "content": {"type": "object", "description": "Structured prompt content"},
                    "description": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["slug", "name", "type", "content"],
            },
        },
        {
            "name": "registry.get",
            "description": "Get a prompt by slug",
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string"}},
                "required": ["slug"],
            },
        },
        {
            "name": "registry.search",
            "description": "Search prompts by query, type, or tags",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "type": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        {
            "name": "vcs.commit",
            "description": "Commit a new version of a prompt",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt_id": {"type": "string"},
                    "content": {"type": "object"},
                    "message": {"type": "string"},
                    "author": {"type": "string"},
                    "branch": {"type": "string", "default": "main"},
                },
                "required": ["prompt_id", "content", "message"],
            },
        },
        {
            "name": "vcs.history",
            "description": "Get version history for a prompt",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt_id": {"type": "string"},
                    "branch": {"type": "string", "default": "main"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["prompt_id"],
            },
        },
        {
            "name": "vcs.diff",
            "description": "Get structural diff between two versions",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt_id": {"type": "string"},
                    "from_version": {"type": "integer"},
                    "to_version": {"type": "integer"},
                },
                "required": ["prompt_id", "from_version", "to_version"],
            },
        },
        {
            "name": "compose.assemble",
            "description": "Compose an agent prompt from components",
            "parameters": {
                "type": "object",
                "properties": {
                    "persona": {"type": "string"},
                    "skills": {"type": "array", "items": {"type": "string"}},
                    "constraints": {"type": "array", "items": {"type": "string"}},
                    "variables": {"type": "object"},
                },
                "required": ["persona"],
            },
        },
        {
            "name": "evaluate.usage_stats",
            "description": "Get usage statistics for a prompt",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt_id": {"type": "string"},
                    "period": {"type": "string", "default": "7d"},
                },
                "required": ["prompt_id"],
            },
        },
    ]
