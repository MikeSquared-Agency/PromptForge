"""Application configuration — reads from environment variables and Docker Swarm secrets."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


def _read_secret(name: str) -> str | None:
    """Read a Docker Swarm secret from /run/secrets/."""
    secret_path = Path(f"/run/secrets/{name}")
    if secret_path.exists():
        return secret_path.read_text().strip()
    return None


def _env_or_secret(env_var: str, secret_name: str) -> str | None:
    """Try environment variable first, then Docker Swarm secret."""
    return os.getenv(env_var) or _read_secret(secret_name)


class Settings(BaseSettings):
    """Application settings with env var and secret support."""

    supabase_url: str = ""
    supabase_key: str = ""
    anthropic_api_key: str = ""
    openclaw_gateway: str = "http://localhost:3000"
    port: int = 8400
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Override with Docker Swarm secrets if available
        if secret := _read_secret("supabase_url"):
            self.supabase_url = secret
        if secret := _read_secret("supabase_key"):
            self.supabase_key = secret
        if secret := _read_secret("anthropic_api_key"):
            self.anthropic_api_key = secret
        if secret := _read_secret("openclaw_gateway"):
            self.openclaw_gateway = secret


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
