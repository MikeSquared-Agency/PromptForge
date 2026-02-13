"""Prompt Injection Scanner — detects injection attempts in prompt content."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Finding:
    """A single scan finding."""

    pattern_name: str
    matched_text: str
    location: str
    severity: str  # low, medium, high, critical
    description: str


@dataclass
class ScanResult:
    """Result of scanning prompt content."""

    clean: bool
    findings: list[Finding] = field(default_factory=list)
    risk_level: str = "low"  # low, medium, high, critical


# Pattern definitions: (name, regex, severity, description)
INSTRUCTION_OVERRIDE_PATTERNS = [
    (
        "ignore_previous",
        r"ignore\s+(all\s+)?previous\s+instructions",
        "critical",
        "Attempts to override previous instructions",
    ),
    (
        "disregard_above",
        r"disregard\s+(everything\s+)?(above|previous)",
        "critical",
        "Attempts to disregard prior context",
    ),
    (
        "forget_everything",
        r"forget\s+everything",
        "critical",
        "Attempts to clear instruction memory",
    ),
    ("new_instructions", r"new\s+instructions\s*:", "critical", "Injects new instructions"),
    (
        "system_prompt_override",
        r"system\s+prompt\s+override",
        "critical",
        "Attempts to override system prompt",
    ),
]

ROLE_MANIPULATION_PATTERNS = [
    ("you_are_now", r"you\s+are\s+now\b", "high", "Attempts to redefine the assistant's role"),
    (
        "pretend_you_are",
        r"pretend\s+(that\s+)?you\s+are",
        "high",
        "Attempts role manipulation via pretending",
    ),
    (
        "act_as_if_instructions",
        r"act\s+as\s+if\s+your\s+instructions",
        "high",
        "Attempts to manipulate instruction interpretation",
    ),
]

DATA_EXFILTRATION_PATTERNS = [
    (
        "repeat_system_prompt",
        r"repeat\s+your\s+system\s+prompt",
        "critical",
        "Attempts to extract system prompt",
    ),
    (
        "output_instructions",
        r"output\s+your\s+instructions",
        "critical",
        "Attempts to extract instructions",
    ),
    ("what_were_you_told", r"what\s+were\s+you\s+told", "high", "Attempts to extract instructions"),
]

# Sections where certain patterns are expected
LENIENT_SECTIONS = {"persona", "identity"}


class PromptScanner:
    """Scans prompt content for injection attempts."""

    def __init__(self, sensitivity: str = "normal") -> None:
        """Initialize scanner.

        Args:
            sensitivity: 'strict' for constraints, 'normal' for general,
                        'lenient' for personas.
        """
        self.sensitivity = sensitivity

    def scan(self, content: dict[str, Any]) -> ScanResult:
        """Scan structured prompt content for injection attempts."""
        all_findings: list[Finding] = []

        for section in content.get("sections", []):
            section_id = section.get("id", "unknown")
            text = section.get("content", "")
            findings = self.scan_text(text, location=f"sections.{section_id}")

            # Filter out false positives for lenient sections
            if section_id in LENIENT_SECTIONS:
                findings = [f for f in findings if f.severity == "critical"]

            all_findings.extend(findings)

        # Scan variables
        for key, value in content.get("variables", {}).items():
            if isinstance(value, str):
                all_findings.extend(self.scan_text(value, location=f"variables.{key}"))

        # Determine risk level
        if any(f.severity == "critical" for f in all_findings):
            risk_level = "critical"
        elif any(f.severity == "high" for f in all_findings):
            risk_level = "high"
        elif any(f.severity == "medium" for f in all_findings):
            risk_level = "medium"
        else:
            risk_level = "low"

        return ScanResult(
            clean=len(all_findings) == 0,
            findings=all_findings,
            risk_level=risk_level,
        )

    def scan_text(self, text: str, location: str = "text") -> list[Finding]:
        """Scan raw text for injection patterns."""
        findings: list[Finding] = []
        text_lower = text.lower()

        # Check instruction override patterns
        for name, pattern, severity, desc in INSTRUCTION_OVERRIDE_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                findings.append(
                    Finding(
                        pattern_name=name,
                        matched_text=match.group(),
                        location=location,
                        severity=severity,
                        description=desc,
                    )
                )

        # Check role manipulation patterns
        for name, pattern, severity, desc in ROLE_MANIPULATION_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                findings.append(
                    Finding(
                        pattern_name=name,
                        matched_text=match.group(),
                        location=location,
                        severity=severity,
                        description=desc,
                    )
                )

        # Check data exfiltration patterns
        for name, pattern, severity, desc in DATA_EXFILTRATION_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                findings.append(
                    Finding(
                        pattern_name=name,
                        matched_text=match.group(),
                        location=location,
                        severity=severity,
                        description=desc,
                    )
                )

        # Check for encoding tricks
        findings.extend(self._check_encoding_tricks(text, location))

        # Check for delimiter attacks
        findings.extend(self._check_delimiter_attacks(text, location))

        return findings

    def _check_encoding_tricks(self, text: str, location: str) -> list[Finding]:
        """Check for base64-encoded instructions, zero-width chars, homoglyphs."""
        findings: list[Finding] = []

        # Zero-width characters
        zero_width = re.findall(r"[\u200b\u200c\u200d\u2060\ufeff]", text)
        if zero_width:
            findings.append(
                Finding(
                    pattern_name="zero_width_chars",
                    matched_text=f"Found {len(zero_width)} zero-width character(s)",
                    location=location,
                    severity="medium",
                    description="Zero-width characters detected — may hide injected content",
                )
            )

        # Base64-encoded blocks that decode to suspicious content
        b64_pattern = re.findall(r"[A-Za-z0-9+/]{20,}={0,2}", text)
        for b64 in b64_pattern:
            try:
                decoded = base64.b64decode(b64).decode("utf-8", errors="ignore").lower()
                suspicious_keywords = ["ignore", "instructions", "system prompt", "you are now"]
                if any(kw in decoded for kw in suspicious_keywords):
                    findings.append(
                        Finding(
                            pattern_name="base64_injection",
                            matched_text=b64[:40] + "...",
                            location=location,
                            severity="high",
                            description="Base64-encoded suspicious content detected",
                        )
                    )
            except Exception:
                pass

        return findings

    def _check_delimiter_attacks(self, text: str, location: str) -> list[Finding]:
        """Check for instructions hidden in code blocks or XML/HTML tags."""
        findings: list[Finding] = []

        # Code blocks with instructions
        code_blocks = re.findall(r"```[\s\S]*?```", text)
        for block in code_blocks:
            inner = block.strip("`").lower()
            if any(kw in inner for kw in ["ignore previous", "new instructions", "system prompt"]):
                findings.append(
                    Finding(
                        pattern_name="code_block_injection",
                        matched_text=block[:60] + "...",
                        location=location,
                        severity="high",
                        description="Instructions hidden in code block",
                    )
                )

        # XML/HTML tags with suspicious content
        tag_content = re.findall(r"<[^>]+>([^<]+)</[^>]+>", text)
        for content in tag_content:
            lower = content.lower()
            if any(kw in lower for kw in ["ignore previous", "new instructions", "system prompt"]):
                findings.append(
                    Finding(
                        pattern_name="tag_injection",
                        matched_text=content[:60],
                        location=location,
                        severity="high",
                        description="Instructions hidden in XML/HTML tags",
                    )
                )

        return findings
