"""Scan endpoint — check content for injection attempts."""

from __future__ import annotations

from fastapi import APIRouter

from prompt_forge.api.models import FindingResponse, ScanRequest, ScanResponse
from prompt_forge.core.scanner import PromptScanner

router = APIRouter()


@router.post("/scan", response_model=ScanResponse)
async def scan_content(data: ScanRequest) -> ScanResponse:
    """Scan prompt content for injection attempts without committing."""
    scanner = PromptScanner(sensitivity=data.sensitivity)
    result = scanner.scan(data.content)
    return ScanResponse(
        clean=result.clean,
        findings=[
            FindingResponse(
                pattern_name=f.pattern_name,
                matched_text=f.matched_text,
                location=f.location,
                severity=f.severity,
                description=f.description,
            )
            for f in result.findings
        ],
        risk_level=result.risk_level,
    )
