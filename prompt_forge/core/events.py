"""NATS event publishing for Hermes integration.

Publishes events on prompt mutations following the Hermes envelope format.
Gracefully degrades if NATS is not available.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog

logger = structlog.get_logger()

_nats_client = None
_nats_available = False

try:
    import nats as nats_lib

    _nats_available = True
except ImportError:
    _nats_available = False


class EventPublisher:
    """Publishes prompt lifecycle events to NATS."""

    def __init__(self, nats_url: str = "nats://localhost:4222") -> None:
        self.nats_url = nats_url
        self._nc = None
        self._connected = False

    async def connect(self) -> bool:
        """Connect to NATS. Returns True if successful."""
        if not _nats_available:
            logger.info("events.nats_not_installed")
            return False
        try:
            self._nc = await nats_lib.connect(self.nats_url)
            self._connected = True
            logger.info("events.nats_connected", url=self.nats_url)
            return True
        except Exception as e:
            logger.warning("events.nats_connect_failed", error=str(e))
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from NATS."""
        if self._nc and self._connected:
            try:
                await self._nc.close()
            except Exception:
                pass
            self._connected = False

    async def publish(
        self,
        event_type: str,
        subject: str,
        data: dict[str, Any],
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> bool:
        """Publish an event in Hermes envelope format.

        Returns True if published, False if NATS unavailable.
        """
        if not self._connected or not self._nc:
            return False

        envelope = {
            "id": str(uuid4()),
            "type": event_type,
            "source": "promptforge",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": correlation_id or str(uuid4()),
            "causation_id": causation_id,
            "data": data,
        }

        try:
            await self._nc.publish(subject, json.dumps(envelope).encode())
            logger.debug("events.published", subject=subject, type=event_type)
            return True
        except Exception as e:
            logger.warning("events.publish_failed", subject=subject, error=str(e))
            return False

    async def publish_prompt_event(
        self,
        slug: str,
        action: str,
        data: dict[str, Any],
    ) -> bool:
        """Publish a prompt lifecycle event."""
        subject = f"swarm.prompt.{slug}.{action}"
        return await self.publish(
            event_type=f"prompt.{action}",
            subject=subject,
            data=data,
        )


# Singleton
_publisher: EventPublisher | None = None


def get_event_publisher() -> EventPublisher:
    """Get the global event publisher (lazy init)."""
    global _publisher
    if _publisher is None:
        nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
        _publisher = EventPublisher(nats_url)
    return _publisher


def publish_event_sync(slug: str, action: str, data: dict[str, Any]) -> None:
    """Fire-and-forget event publish from sync code."""
    publisher = get_event_publisher()
    if not publisher._connected:
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(publisher.publish_prompt_event(slug, action, data))
        else:
            loop.run_until_complete(publisher.publish_prompt_event(slug, action, data))
    except Exception:
        pass  # Best-effort
