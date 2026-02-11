"""Main API router — aggregates all endpoint modules."""

from fastapi import APIRouter

from prompt_forge.api.compose import router as compose_router
from prompt_forge.api.prompts import router as prompts_router
from prompt_forge.api.usage import router as usage_router
from prompt_forge.api.versions import router as versions_router

api_router = APIRouter()

api_router.include_router(prompts_router, prefix="/prompts", tags=["prompts"])
api_router.include_router(versions_router, prefix="/prompts", tags=["versions"])
api_router.include_router(compose_router, tags=["composition"])
api_router.include_router(usage_router, prefix="/usage", tags=["usage"])
