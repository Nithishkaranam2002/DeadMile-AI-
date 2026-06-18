"""Kafka producer for publishing parsed load records."""

from __future__ import annotations

import json
import time
from typing import Any

import structlog
from confluent_kafka import Producer
from confluent_kafka import KafkaException

from shared.config import settings
from shared.models import LoadRecord

logger = structlog.get_logger(__name__)


class LoadKafkaProducer:
    """Publishes LoadRecord messages to Kafka with retry logic."""

    def __init__(self, bootstrap_servers: str | None = None, topic: str | None = None) -> None:
        self.topic = topic or settings.kafka_topic_loads
        self._producer = Producer(
            {
                "bootstrap.servers": bootstrap_servers or settings.kafka_bootstrap_servers,
                "client.id": "deadmile-load-ingestion",
                "acks": "all",
                "retries": 3,
                "message.max.bytes": 1048576,
            }
        )
        self.published_count = 0
        self.failed_count = 0

    def _delivery_callback(self, err: Any, msg: Any) -> None:
        if err is not None:
            self.failed_count += 1
            logger.error("kafka_delivery_failed", error=str(err), key=msg.key())
        else:
            self.published_count += 1

    def _serialize_load(self, load: LoadRecord) -> bytes:
        payload = load.model_dump(mode="json")
        return json.dumps(payload).encode("utf-8")

    def publish(self, load: LoadRecord, max_retries: int = 3) -> bool:
        """Publish a single load with exponential backoff retries."""
        payload = self._serialize_load(load)
        key = load.load_id.encode("utf-8")

        for attempt in range(max_retries):
            try:
                self._producer.produce(
                    topic=self.topic,
                    key=key,
                    value=payload,
                    callback=self._delivery_callback,
                )
                self._producer.poll(0)
                return True
            except BufferError:
                self._producer.poll(1)
            except KafkaException as exc:
                wait = 2**attempt
                logger.warning(
                    "kafka_publish_retry",
                    load_id=load.load_id,
                    attempt=attempt + 1,
                    wait_seconds=wait,
                    error=str(exc),
                )
                time.sleep(wait)

        self.failed_count += 1
        logger.error("kafka_publish_failed", load_id=load.load_id, retries=max_retries)
        return False

    def publish_batch(self, loads: list[LoadRecord]) -> dict[str, int]:
        """Publish multiple loads and flush."""
        for load in loads:
            self.publish(load)
        remaining = self._producer.flush(timeout=30)
        if remaining > 0:
            logger.error("kafka_flush_incomplete", remaining=remaining)
        return {
            "published": self.published_count,
            "failed": self.failed_count,
            "total": len(loads),
        }

    def close(self) -> None:
        self._producer.flush(timeout=10)
