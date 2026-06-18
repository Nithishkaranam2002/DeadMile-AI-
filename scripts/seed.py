"""Full data seeding pipeline for DeadMile AI."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import sys
import time
from pathlib import Path

import httpx
import structlog

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.config import settings

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
)
logger = structlog.get_logger(__name__)


def _clear_app_modules() -> None:
    for key in list(sys.modules):
        if key == "app" or key.startswith("app."):
            del sys.modules[key]


def _import_from_service(service: str, module_path: str):
    service_dir = str(ROOT / "services" / service)
    if service_dir not in sys.path:
        sys.path.insert(0, service_dir)
    return importlib.import_module(module_path)


def parse_all_loads(text_only: bool = False, pdf_only: bool = False) -> list:
    _clear_app_modules()
    text_parser = _import_from_service("load-ingestion", "app.parsers.text_parser").TextParser()
    pdf_parser = _import_from_service("load-ingestion", "app.parsers.pdf_parser").PDFParser()

    records = []
    if not pdf_only:
        records.extend(text_parser.parse_all_files(settings.data_text_path))
    if not text_only:
        records.extend(pdf_parser.parse_all_pdfs(settings.data_pdf_path))
    return records


async def seed_direct(records: list) -> dict:
    _clear_app_modules()
    db = _import_from_service("load-processor", "app.db")
    rate_history = _import_from_service("load-processor", "app.rate_history")

    logger.info("direct_db_insert", count=len(records))
    inserted = 0
    batch_size = 100
    for i in range(0, len(records), batch_size):
        inserted += await db.insert_loads_batch(records[i : i + batch_size])

    markets = await db.compute_market_scores()
    lanes = await rate_history.populate_rate_history()
    stats = await db.get_stats()
    await db.close_pool()
    return {
        "inserted": inserted,
        "market_scores_updated": markets,
        "rate_history_lanes": lanes,
        "stats": stats,
    }


def seed_via_kafka(records: list) -> dict:
    _clear_app_modules()
    producer_mod = _import_from_service("load-ingestion", "app.kafka_producer")
    producer = producer_mod.LoadKafkaProducer()
    result = producer.publish_batch(records)
    producer.close()
    return result


def seed_via_http() -> dict:
    with httpx.Client(timeout=120.0) as client:
        ingest = client.post("http://load-ingestion:8002/ingest/all")
        ingest.raise_for_status()
        logger.info("http_ingest_complete", result=ingest.json())
        time.sleep(15)
        flush = client.post("http://load-processor:8003/flush")
        flush.raise_for_status()
        return flush.json()


async def main() -> None:
    parser = argparse.ArgumentParser(description="DeadMile AI seed pipeline")
    parser.add_argument("--mode", choices=["direct", "kafka", "http"], default="http")
    parser.add_argument("--text-only", action="store_true")
    parser.add_argument("--pdf-only", action="store_true")
    args = parser.parse_args()

    if args.mode == "http":
        result = seed_via_http()
    else:
        records = parse_all_loads(text_only=args.text_only, pdf_only=args.pdf_only)
        logger.info("parsed_records", count=len(records))
        if not records:
            logger.warning("no_records_found")
            return
        if args.mode == "direct":
            result = await seed_direct(records)
        else:
            kafka_result = seed_via_kafka(records)
            logger.info("kafka_publish", **kafka_result)
            time.sleep(15)
            _clear_app_modules()
            consumer_mod = _import_from_service("load-processor", "app.kafka_consumer")
            db = _import_from_service("load-processor", "app.db")
            consumer = consumer_mod.get_consumer()
            consumer.set_event_loop(asyncio.get_running_loop())
            result = await consumer.finalize_pipeline()
            await db.close_pool()

    logger.info("seed_complete", result=result)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
