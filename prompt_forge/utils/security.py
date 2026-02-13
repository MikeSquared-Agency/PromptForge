"""Security utilities — secret scanning, input validation."""

from __future__ import annotations

import re
from typing import Any


# Patterns that might indicate leaked secrets
SECRET_PATTERNS = [
    re.compile(r"sk-ant-[a-zA-Z0-9-]{20,}"),  # Anthropic API key
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # OpenAI API key
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),  # GitHub PAT
    re.compile(r"eyJ[a-zA-Z0-9_-]{50,}"),  # JWT tokens
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key
    re.compile(r"xox[bporas]-[a-zA-Z0-9-]+"),  # Slack tokens
]

MAX_CONTENT_SIZE = 50 * 1024  # 50KB default
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")


def scan_for_secrets(text: str) -> list[str]:
    """Scan text for potential secrets. Returns list of detected pattern names."""
    findings: list[str] = []
    pattern_names = [
        "Anthropic API key",
        "OpenAI API key",
        "GitHub PAT",
        "JWT token",
        "AWS access key",
        "Slack token",
    ]
    for pattern, name in zip(SECRET_PATTERNS, pattern_names):
        if pattern.search(text):
            findings.append(name)
    return findings


def validate_content_size(content: dict[str, Any], max_bytes: int = MAX_CONTENT_SIZE) -> bool:
    """Check that serialised content doesn't exceed size limit."""
    import json

    return len(json.dumps(content).encode()) <= max_bytes


def validate_slug(slug: str) -> bool:
    """Validate slug format: lowercase alphanumeric with hyphens, 2-100 chars."""
    return bool(SLUG_PATTERN.match(slug)) and 2 <= len(slug) <= 100


def sanitise_content(content: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Sanitise prompt content — scan for secrets and validate size.

    Returns (content, warnings).
    """
    import json

    warnings: list[str] = []

    text = json.dumps(content)
    secrets = scan_for_secrets(text)
    if secrets:
        warnings.append(f"Potential secrets detected: {', '.join(secrets)}")

    if not validate_content_size(content):
        warnings.append(f"Content exceeds {MAX_CONTENT_SIZE // 1024}KB limit")

    return content, warnings
