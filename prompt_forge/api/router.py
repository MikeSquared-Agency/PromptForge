"""Main API router — aggregates all endpoint modules."""

from fastapi import APIRouter

from prompt_forge.api.agents import router as agents_router
from prompt_forge.api.architect import router as architect_router
from prompt_forge.api.audit import router as audit_router
from prompt_forge.api.branches import router as branches_router
from prompt_forge.api.compose import router as compose_router
from prompt_forge.api.effectiveness import router as effectiveness_router
from prompt_forge.api.persona_prompts import router as persona_prompts_router
from prompt_forge.api.prompts import router as prompts_router
from prompt_forge.api.scan import router as scan_router
from prompt_forge.api.subscriptions import router as subscriptions_router
from prompt_forge.api.usage import router as usage_router
from prompt_forge.api.versions import router as versions_router

api_router = APIRouter()

api_router.include_router(prompts_router, prefix="/prompts", tags=["prompts"])
api_router.include_router(versions_router, prefix="/prompts", tags=["versions"])
api_router.include_router(branches_router, prefix="/prompts", tags=["branches"])
api_router.include_router(subscriptions_router, prefix="/prompts", tags=["subscriptions"])
api_router.include_router(
    persona_prompts_router, prefix="/persona-prompts", tags=["persona-prompts"]
)
api_router.include_router(agents_router, prefix="/agents", tags=["agents"])
api_router.include_router(compose_router, tags=["composition"])
api_router.include_router(usage_router, prefix="/usage", tags=["usage"])
api_router.include_router(scan_router, tags=["scanning"])
api_router.include_router(audit_router, tags=["audit"])
api_router.include_router(architect_router, tags=["architect"])
api_router.include_router(effectiveness_router, tags=["effectiveness"])
