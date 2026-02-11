"""PromptArchitect conversation endpoints.

TODO Phase 2: Full conversational architect with streaming responses.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/architect", tags=["architect"])


# TODO Phase 2: Implement architect endpoints
# POST /architect/design — Design a new prompt from requirements
# POST /architect/refine — Refine an existing prompt
# POST /architect/evaluate — Evaluate prompt performance
