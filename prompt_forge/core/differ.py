"""Structural diffing engine for JSON prompt content."""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from typing import Any


class StructuralDiffer:
    """Computes section-level diffs between prompt content versions."""

    def diff(
        self,
        old_content: dict[str, Any],
        new_content: dict[str, Any],
    ) -> dict[str, Any]:
        """Compute structural diff between two prompt content objects.

        Compares section-by-section, detecting added, removed, and modified sections.
        """
        old_sections = {s["id"]: s for s in old_content.get("sections", [])}
        new_sections = {s["id"]: s for s in new_content.get("sections", [])}

        changes: list[dict[str, Any]] = []

        # Check for removed and modified sections
        for section_id, old_section in old_sections.items():
            if section_id not in new_sections:
                changes.append({
                    "section_id": section_id,
                    "type": "removed",
                    "content": old_section.get("content", ""),
                })
            else:
                new_section = new_sections[section_id]
                old_text = old_section.get("content", "")
                new_text = new_section.get("content", "")
                if old_text != new_text:
                    similarity = SequenceMatcher(None, old_text, new_text).ratio()
                    changes.append({
                        "section_id": section_id,
                        "type": "modified",
                        "before": old_text,
                        "after": new_text,
                        "similarity": round(similarity, 2),
                    })

        # Check for added sections
        for section_id, new_section in new_sections.items():
            if section_id not in old_sections:
                changes.append({
                    "section_id": section_id,
                    "type": "added",
                    "content": new_section.get("content", ""),
                })

        # Check for variable changes
        old_vars = old_content.get("variables", {})
        new_vars = new_content.get("variables", {})
        if old_vars != new_vars:
            changes.append({
                "section_id": "_variables",
                "type": "modified",
                "before": old_vars,
                "after": new_vars,
            })

        # Check for metadata changes
        old_meta = old_content.get("metadata", {})
        new_meta = new_content.get("metadata", {})
        if old_meta != new_meta:
            changes.append({
                "section_id": "_metadata",
                "type": "modified",
                "before": old_meta,
                "after": new_meta,
            })

        # Build summary
        added = sum(1 for c in changes if c["type"] == "added")
        removed = sum(1 for c in changes if c["type"] == "removed")
        modified = sum(1 for c in changes if c["type"] == "modified")

        parts = []
        if added:
            parts.append(f"{added} section(s) added")
        if removed:
            parts.append(f"{removed} section(s) removed")
        if modified:
            parts.append(f"{modified} section(s) modified")

        return {
            "changes": changes,
            "summary": ", ".join(parts) if parts else "No changes",
        }

    def field_diff(
        self,
        old_content: dict[str, Any],
        new_content: dict[str, Any],
        from_version: int,
        to_version: int,
    ) -> dict[str, Any]:
        """Compute a field-level diff comparing top-level keys between versions.

        Returns the format specified in the version-safety spec:
        changes array with field/action/from_length/to_length, and summary.
        """
        old_keys = set(old_content.keys())
        new_keys = set(new_content.keys())

        changes: list[dict[str, Any]] = []

        # Removed fields
        for key in sorted(old_keys - new_keys):
            changes.append({"field": key, "action": "removed"})

        # Added fields
        for key in sorted(new_keys - old_keys):
            changes.append({"field": key, "action": "added"})

        # Shared fields: modified or unchanged
        modified_count = 0
        unchanged_count = 0
        for key in sorted(old_keys & new_keys):
            old_val = old_content[key]
            new_val = new_content[key]
            if old_val == new_val:
                unchanged_count += 1
            else:
                old_len = len(json.dumps(old_val, ensure_ascii=False))
                new_len = len(json.dumps(new_val, ensure_ascii=False))
                changes.append({
                    "field": key,
                    "action": "modified",
                    "from_length": old_len,
                    "to_length": new_len,
                })
                modified_count += 1

        added_count = len(new_keys - old_keys)
        removed_count = len(old_keys - new_keys)

        old_total = len(json.dumps(old_content, ensure_ascii=False))
        new_total = len(json.dumps(new_content, ensure_ascii=False))
        if old_total > 0:
            content_change_pct = round((new_total - old_total) / old_total * 100, 1)
        else:
            content_change_pct = 0.0

        return {
            "from_version": from_version,
            "to_version": to_version,
            "changes": changes,
            "summary": {
                "added": added_count,
                "removed": removed_count,
                "modified": modified_count,
                "unchanged": unchanged_count,
                "content_change_pct": content_change_pct,
            },
        }

    def human_readable(self, diff_result: dict[str, Any]) -> str:
        """Format a diff result as human-readable text."""
        lines = [f"Summary: {diff_result['summary']}", ""]
        for change in diff_result["changes"]:
            section = change["section_id"]
            ctype = change["type"]
            if ctype == "added":
                lines.append(f"+ [{section}] Added: {change['content'][:100]}...")
            elif ctype == "removed":
                lines.append(f"- [{section}] Removed: {change['content'][:100]}...")
            elif ctype == "modified":
                sim = change.get("similarity", "?")
                lines.append(f"~ [{section}] Modified (similarity: {sim})")
                lines.append(f"  Before: {str(change['before'])[:80]}...")
                lines.append(f"  After:  {str(change['after'])[:80]}...")
        return "\n".join(lines)
