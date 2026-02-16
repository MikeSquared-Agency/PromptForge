"""NATS subscribers for effectiveness data collection.

Listens to:
- swarm.usage.tokens — upserts token data by session_uuid
- swarm.dredd.correction — increments correction_count by session_uuid
- swarm.cc.session.completed — updates completion metadata
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()

_nats_available = False
try:
    import nats as nats_lib

    _nats_available = True
except ImportError:
    pass


class EffectivenessSubscriber:
    """Subscribes to NATS events and updates prompt_effectiveness records."""

    def __init__(self, nats_url: str = "nats://localhost:4222") -> None:
        self.nats_url = nats_url
        self._nc = None
        self._subs = []
        self._connected = False

    async def connect(self) -> bool:
        if not _nats_available:
            logger.info("subscribers.nats_not_installed")
            return False
        try:
            self._nc = await nats_lib.connect(self.nats_url)
            self._connected = True
            logger.info("subscribers.connected", url=self.nats_url)
            return True
        except Exception as e:
            logger.warning("subscribers.connect_failed", error=str(e))
            return False

    async def start(self) -> None:
        if not self._connected:
            return

        sub1 = await self._nc.subscribe("swarm.usage.tokens", cb=self._handle_token_usage)
        sub2 = await self._nc.subscribe("swarm.dredd.correction", cb=self._handle_correction)
        sub3 = await self._nc.subscribe(
            "swarm.cc.session.completed", cb=self._handle_session_completed
        )
        self._subs = [sub1, sub2, sub3]
        logger.info(
            "subscribers.started",
            subjects=["swarm.usage.tokens", "swarm.dredd.correction", "swarm.cc.session.completed"],
        )

    async def stop(self) -> None:
        for sub in self._subs:
            try:
                await sub.unsubscribe()
            except Exception:
                pass
        if self._nc and self._connected:
            try:
                await self._nc.close()
            except Exception:
                pass
        self._connected = False
        logger.info("subscribers.stopped")

    async def _handle_token_usage(self, msg) -> None:
        """Handle swarm.usage.tokens — upsert token data by session_uuid."""
        try:
            payload = json.loads(msg.data.decode())
            data = payload.get("data", payload)
            session_uuid = data.get("session_uuid")
            if not session_uuid:
                return

            from prompt_forge.db.client import get_supabase_client

            db = get_supabase_client()

            rows = db.select("prompt_effectiveness", filters={"session_uuid": session_uuid})
            if rows:
                updates = {}
                if data.get("input_tokens"):
                    updates["input_tokens"] = data["input_tokens"]
                if data.get("output_tokens"):
                    updates["output_tokens"] = data["output_tokens"]
                if data.get("total_tokens"):
                    updates["total_tokens"] = data["total_tokens"]
                if data.get("cost_usd"):
                    updates["cost_usd"] = data["cost_usd"]
                if data.get("model_tier") and not rows[0].get("model_tier"):
                    updates["model_tier"] = data["model_tier"]
                if updates:
                    db.update("prompt_effectiveness", rows[0]["id"], updates)
                    logger.debug("subscribers.tokens_updated", session=session_uuid)
            else:
                logger.debug("subscribers.tokens_no_record", session=session_uuid)
        except Exception as e:
            logger.warning("subscribers.token_usage_error", error=str(e))

    async def _handle_correction(self, msg) -> None:
        """Handle swarm.dredd.correction — increment correction_count."""
        try:
            payload = json.loads(msg.data.decode())
            data = payload.get("data", payload)
            session_ref = data.get("session_ref")
            if not session_ref:
                return

            from prompt_forge.db.client import get_supabase_client

            db = get_supabase_client()

            rows = db.select("prompt_effectiveness", filters={"session_uuid": session_ref})
            if not rows:
                return

            row = rows[0]
            updates = {"correction_count": (row.get("correction_count", 0) or 0) + 1}

            correction_type = data.get("correction_type", "")
            if correction_type == "rejected":
                current_score = row.get("outcome_score")
                if current_score is not None:
                    updates["outcome_score"] = max(0.0, current_score - 0.1)
                else:
                    updates["outcome_score"] = 0.5
            elif correction_type == "confirmed":
                current_score = row.get("outcome_score")
                if current_score is not None:
                    updates["outcome_score"] = min(1.0, current_score + 0.05)
                else:
                    updates["outcome_score"] = 0.8

            db.update("prompt_effectiveness", row["id"], updates)
            logger.debug(
                "subscribers.correction_applied", session=session_ref, type=correction_type
            )
        except Exception as e:
            logger.warning("subscribers.correction_error", error=str(e))

    async def _handle_session_completed(self, msg) -> None:
        """Handle swarm.cc.session.completed — update completion metadata."""
        try:
            payload = json.loads(msg.data.decode())
            data = payload.get("data", payload)
            session_id = data.get("session_id")
            if not session_id:
                return

            from prompt_forge.db.client import get_supabase_client

            db = get_supabase_client()

            rows = db.select("prompt_effectiveness", filters={"session_uuid": session_id})
            if not rows:
                return

            row = rows[0]
            updates = {"completed_at": datetime.now(timezone.utc).isoformat()}

            exit_code = data.get("exit_code")
            if exit_code == 0 and not row.get("outcome_score"):
                updates["outcome"] = "success"
                updates["outcome_score"] = 0.7
            elif exit_code and exit_code != 0 and not row.get("outcome_score"):
                updates["outcome"] = "failure"
                updates["outcome_score"] = 0.2

            if data.get("task_id") and not row.get("task_id"):
                updates["task_id"] = data["task_id"]

            db.update("prompt_effectiveness", row["id"], updates)
            logger.debug("subscribers.session_completed", session=session_id)
        except Exception as e:
            logger.warning("subscribers.session_completed_error", error=str(e))


_subscriber: EffectivenessSubscriber | None = None


def get_effectiveness_subscriber() -> EffectivenessSubscriber:
    import os

    global _subscriber
    if _subscriber is None:
        nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
        _subscriber = EffectivenessSubscriber(nats_url)
    return _subscriber
