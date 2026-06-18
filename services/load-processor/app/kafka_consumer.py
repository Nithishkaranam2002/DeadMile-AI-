"""Kafka consumer for raw load events."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import structlog
from confluent_kafka import Consumer, KafkaError, KafkaException

from app.db import compute_market_scores, insert_loads_batch
from app.rate_history import populate_rate_history
from shared.config import settings
from shared.models import LoadRecord

logger = structlog.get_logger(__name__)

BATCH_SIZE = 100


class LoadKafkaConsumer:
    """Consumes raw-loads topic and persists to PostgreSQL."""

    def __init__(self) -> None:
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.processed_count = 0
        self.error_count = 0
        self._batch: list[LoadRecord] = []
        self._consumer = Consumer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "group.id": settings.kafka_group_load_processor,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": True,
                "session.timeout.ms": 30000,
            }
        )

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def _write_batch(self, batch: list[LoadRecord]) -> None:
        try:
            count = await insert_loads_batch(batch)
            self.processed_count += count
            logger.info("batch_inserted", count=count)
        except Exception as exc:
            self.error_count += len(batch)
            logger.error("batch_insert_failed", error=str(exc), count=len(batch))

    def _flush_batch(self) -> None:
        if not self._batch:
            return
        batch = self._batch[:]
        self._batch.clear()
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._write_batch(batch), self._loop)
            future.result(timeout=60)
        else:
            asyncio.run(self._write_batch(batch))

    def _process_message(self, value: bytes) -> None:
        try:
            data = json.loads(value.decode("utf-8"))
            load = LoadRecord.model_validate(data)
            self._batch.append(load)
            if len(self._batch) >= BATCH_SIZE:
                self._flush_batch()
        except Exception as exc:
            self.error_count += 1
            logger.warning("message_deserialize_failed", error=str(exc))

    def _run_loop(self) -> None:
        self._consumer.subscribe([settings.kafka_topic_loads])
        logger.info("kafka_consumer_started", topic=settings.kafka_topic_loads)

        try:
            while self._running:
                msg = self._consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    logger.error("kafka_consumer_error", error=str(msg.error()))
                    continue
                if msg.value():
                    self._process_message(msg.value())
        except KafkaException as exc:
            logger.error("kafka_consumer_fatal", error=str(exc))
        finally:
            self._flush_batch()
            self._consumer.close()
            logger.info("kafka_consumer_stopped")

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="kafka-consumer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)

    def flush(self) -> None:
        self._flush_batch()

    async def finalize_pipeline(self) -> dict[str, Any]:
        self.flush()
        markets = await compute_market_scores()
        lanes = await populate_rate_history()
        return {
            "processed": self.processed_count,
            "errors": self.error_count,
            "market_scores_updated": markets,
            "rate_history_lanes": lanes,
        }

    def get_status(self) -> dict[str, int]:
        return {
            "processed": self.processed_count,
            "errors": self.error_count,
            "pending_batch": len(self._batch),
        }


_consumer: LoadKafkaConsumer | None = None


def get_consumer() -> LoadKafkaConsumer:
    global _consumer
    if _consumer is None:
        _consumer = LoadKafkaConsumer()
    return _consumer
