"""Tests for event publishing."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prompt_forge.core.events import EventPublisher


class TestEventPublisher:
    def test_init(self):
        pub = EventPublisher("nats://localhost:4222")
        assert pub.nats_url == "nats://localhost:4222"
        assert not pub._connected

    @pytest.mark.asyncio
    async def test_publish_when_not_connected(self):
        pub = EventPublisher()
        result = await pub.publish("test.event", "test.subject", {"key": "value"})
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_prompt_event_when_not_connected(self):
        pub = EventPublisher()
        result = await pub.publish_prompt_event("my-prompt", "updated", {"version": 1})
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_when_connected(self):
        pub = EventPublisher()
        pub._connected = True
        pub._nc = MagicMock()
        pub._nc.publish = AsyncMock()

        result = await pub.publish("test.event", "test.subject", {"key": "value"})
        assert result is True
        pub._nc.publish.assert_called_once()

        # Verify envelope format
        call_args = pub._nc.publish.call_args
        subject = call_args[0][0]
        payload = json.loads(call_args[0][1].decode())
        assert subject == "test.subject"
        assert payload["type"] == "test.event"
        assert payload["source"] == "promptforge"
        assert "id" in payload
        assert "timestamp" in payload
        assert "correlation_id" in payload
        assert payload["data"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_publish_prompt_event_subject_format(self):
        pub = EventPublisher()
        pub._connected = True
        pub._nc = MagicMock()
        pub._nc.publish = AsyncMock()

        await pub.publish_prompt_event("my-prompt", "updated", {"v": 1})
        call_args = pub._nc.publish.call_args
        subject = call_args[0][0]
        assert subject == "swarm.prompt.my-prompt.updated"

    @pytest.mark.asyncio
    async def test_publish_handles_error_gracefully(self):
        pub = EventPublisher()
        pub._connected = True
        pub._nc = MagicMock()
        pub._nc.publish = AsyncMock(side_effect=Exception("connection lost"))

        result = await pub.publish("test", "test.sub", {})
        assert result is False

    @pytest.mark.asyncio
    async def test_disconnect(self):
        pub = EventPublisher()
        pub._connected = True
        pub._nc = MagicMock()
        pub._nc.close = AsyncMock()

        await pub.disconnect()
        assert not pub._connected
        pub._nc.close.assert_called_once()
