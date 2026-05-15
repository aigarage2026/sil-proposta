"""
`portal.events` consumer loop (v3 §12.4).

Runs as a background asyncio task started in main.py's lifespan. Reads
batches via XREADGROUP, dispatches to handlers, XACK on success. On
handler failure the message is left unacked — Redis Streams keeps it in
the consumer's pending list and will redeliver on next reconnect (and a
future operator pass can XCLAIM stuck messages between consumers).

Lifecycle:
  start_consumer() → returns the task. Cancel the task to stop.
  The loop traps CancelledError so it exits cleanly.

Settings:
  EVENT_CONSUMER_ENABLED — default False. Set True to start the loop.
  EVENT_CONSUMER_NAME    — default `{slug}-1`. Set per-replica in prod.
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

from core.database import async_session
from core.event_bus import (
    CONSUMER_GROUP,
    PORTAL_EVENTS_STREAM,
    EventBus,
    get_event_bus,
)
from core.logger import get_logger
from services.events.handlers import dispatch

logger = get_logger()


async def _process_batch(
    bus: EventBus,
    consumer_name: str,
    count: int,
    block_ms: int,
) -> int:
    messages = await bus.read_group(
        stream=PORTAL_EVENTS_STREAM,
        group=CONSUMER_GROUP,
        consumer=consumer_name,
        count=count,
        block_ms=block_ms,
    )
    if not messages:
        return 0

    processed = 0
    async with async_session() as db:
        for msg_id, payload in messages:
            ok = await dispatch(payload, db)
            if ok:
                try:
                    await bus.ack(PORTAL_EVENTS_STREAM, CONSUMER_GROUP, msg_id)
                    processed += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("event_ack_failed", msg_id=msg_id, error=str(exc))
            else:
                logger.warning("event_left_pending", msg_id=msg_id, type=payload.get("type"))
    return processed


async def consumer_loop(
    bus: Optional[EventBus] = None,
    consumer_name: Optional[str] = None,
    count: int = 10,
    block_ms: int = 5000,
) -> None:
    """Main consumer loop. Cancel the surrounding Task to stop."""
    bus = bus or get_event_bus()
    consumer_name = consumer_name or os.getenv("EVENT_CONSUMER_NAME", "sil-proposta-1")

    try:
        await bus.ensure_consumer_group(PORTAL_EVENTS_STREAM, CONSUMER_GROUP)
    except Exception as exc:  # noqa: BLE001
        logger.error("event_consumer_group_init_failed", error=str(exc))
        return

    logger.info("event_consumer_started", consumer=consumer_name, stream=PORTAL_EVENTS_STREAM)
    try:
        while True:
            try:
                await _process_batch(bus, consumer_name, count, block_ms)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("event_consumer_batch_failed", error=str(exc))
                await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        logger.info("event_consumer_stopped", consumer=consumer_name)
        raise


def start_consumer(bus: Optional[EventBus] = None) -> asyncio.Task:
    """Spawn the loop as a background task. Returns the Task so the caller
    can cancel it during shutdown.
    """
    return asyncio.create_task(consumer_loop(bus=bus), name="portal-events-consumer")
