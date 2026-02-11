"""API client for the PromptForge REST API."""

from __future__ import annotations

from typing import Any

import httpx


class ForgeClient:
    """HTTP client wrapping all PromptForge API endpoints."""

    def __init__(self, base_url: str = "http://localhost:8100", auth_token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        headers = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        self._client = httpx.Client(base_url=f"{self.base_url}/api/v1", headers=headers, timeout=30)

    def _handle(self, resp: httpx.Response) -> Any:
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise RuntimeError(f"API error ({resp.status_code}): {detail}")
        return resp.json()

    # --- Prompts ---

    def list_prompts(self, **params: Any) -> list[dict]:
        return self._handle(self._client.get("/prompts", params=params))

    def create_prompt(self, data: dict) -> dict:
        return self._handle(self._client.post("/prompts", json=data))

    def get_prompt(self, slug: str) -> dict:
        return self._handle(self._client.get(f"/prompts/{slug}"))

    def archive_prompt(self, slug: str) -> None:
        resp = self._client.delete(f"/prompts/{slug}")
        if resp.status_code >= 400:
            raise RuntimeError(f"API error ({resp.status_code})")

    # --- Versions ---

    def commit_version(self, slug: str, data: dict) -> dict:
        return self._handle(self._client.post(f"/prompts/{slug}/versions", json=data))

    def list_versions(self, slug: str, branch: str = "main") -> list[dict]:
        return self._handle(self._client.get(f"/prompts/{slug}/versions", params={"branch": branch}))

    def diff_versions(self, slug: str, v1: int, v2: int, branch: str = "main") -> dict:
        return self._handle(self._client.get(
            f"/prompts/{slug}/diff",
            params={"from": v1, "to": v2, "branch": branch},
        ))

    def rollback(self, slug: str, version: int, author: str = "system") -> dict:
        return self._handle(self._client.post(
            f"/prompts/{slug}/rollback",
            json={"version": version, "author": author},
        ))

    # --- Composition ---

    def compose(self, data: dict) -> dict:
        return self._handle(self._client.post("/compose", json=data))

    def resolve(self, data: dict) -> dict:
        return self._handle(self._client.post("/resolve", json=data))

    # --- Scanning ---

    def scan(self, content: dict, sensitivity: str = "normal") -> dict:
        return self._handle(self._client.post("/scan", json={"content": content, "sensitivity": sensitivity}))

    # --- Audit ---

    def audit_query(self, **params: Any) -> list[dict]:
        return self._handle(self._client.get("/audit", params=params))

    def audit_entity(self, entity_type: str, entity_id: str) -> list[dict]:
        return self._handle(self._client.get(f"/audit/{entity_type}/{entity_id}"))

    # --- Search ---

    def search(self, query: str) -> list[dict]:
        return self._handle(self._client.get("/prompts", params={"search": query}))
