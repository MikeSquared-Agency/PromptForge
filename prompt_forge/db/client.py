"""Supabase client initialization and helper methods."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import structlog

from prompt_forge.config import get_settings

try:
    from supabase import Client, create_client
except ImportError:
    Client = None  # type: ignore
    create_client = None  # type: ignore

logger = structlog.get_logger()


class SupabaseClient:
    """Wrapper around the Supabase client with convenience methods."""

    def __init__(self, client: Client) -> None:
        self._client = client

    @property
    def client(self) -> Client:
        """Access the raw Supabase client."""
        return self._client

    def insert(self, table: str, data: dict[str, Any]) -> dict[str, Any]:
        """Insert a record and return the created row."""
        result = self._client.table(table).insert(data).execute()
        return result.data[0]

    def select(
        self,
        table: str,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        ascending: bool = True,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Select records with optional filters, ordering, and limit."""
        query = self._client.table(table).select("*")

        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)

        if order_by:
            query = query.order(order_by, desc=not ascending)

        if limit:
            query = query.limit(limit)

        result = query.execute()
        return result.data

    def update(self, table: str, id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a record by ID."""
        result = self._client.table(table).update(data).eq("id", id).execute()
        return result.data[0]

    def delete(self, table: str, id: str) -> None:
        """Delete a record by ID."""
        self._client.table(table).delete().eq("id", id).execute()


@lru_cache
def get_supabase_client() -> SupabaseClient:
    """Get cached Supabase client instance."""
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_key)
    logger.info("supabase.connected", url=settings.supabase_url)
    return SupabaseClient(client)
