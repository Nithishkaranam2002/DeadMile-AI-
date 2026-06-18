"""DeadMile AI — Load Ingestion Service"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

import structlog
from fastapi import FastAPI, HTTPException
from prometheus_client import make_asgi_app

from app.kafka_producer import LoadKafkaProducer
from app.parsers.pdf_parser import PDFParser
from app.parsers.text_parser import TextParser
from shared.config import settings

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger(__name__)

_stats: dict[str, Any] = {
    "text_parsed": 0,
    "pdf_parsed": 0,
    "kafka_published": 0,
    "kafka_failed": 0,
    "by_format": Counter(),
    "by_equipment": Counter(),
    "by_source": Counter(),
}


def _ingest_records(records: list, source_label: str) -> dict[str, Any]:
    if not records:
        return {"parsed": 0, "published": 0, "failed": 0}

    producer = LoadKafkaProducer()
    result = producer.publish_batch(records)
    producer.close()

    for record in records:
        _stats["by_format"][record.format_type or "unknown"] += 1
        _stats["by_equipment"][record.equipment] += 1
        _stats["by_source"][record.source] += 1

    if source_label == "text":
        _stats["text_parsed"] += len(records)
    else:
        _stats["pdf_parsed"] += len(records)

    _stats["kafka_published"] += result["published"]
    _stats["kafka_failed"] += result["failed"]

    logger.info("ingestion_complete", source=source_label, **result)
    return {"parsed": len(records), **result}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("load_ingestion_started", text_path=settings.data_text_path, pdf_path=settings.data_pdf_path)
    yield


app = FastAPI(
    title="DeadMile AI — Load Ingestion",
    description="Parses text and PDF load files, publishes to Kafka",
    version="0.2.0",
    lifespan=lifespan,
)

app.mount("/metrics", make_asgi_app())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "load-ingestion"}


@app.get("/stats")
async def stats() -> dict[str, Any]:
    return {
        "text_parsed": _stats["text_parsed"],
        "pdf_parsed": _stats["pdf_parsed"],
        "kafka_published": _stats["kafka_published"],
        "kafka_failed": _stats["kafka_failed"],
        "by_format": dict(_stats["by_format"]),
        "by_equipment": dict(_stats["by_equipment"]),
        "by_source": dict(_stats["by_source"]),
    }


@app.post("/ingest/text")
async def ingest_text() -> dict[str, Any]:
    text_dir = Path(settings.data_text_path)
    if not text_dir.exists():
        raise HTTPException(status_code=404, detail=f"Text directory not found: {text_dir}")

    parser = TextParser()
    records = parser.parse_all_files(str(text_dir))
    return _ingest_records(records, "text")


@app.post("/ingest/pdf")
async def ingest_pdf() -> dict[str, Any]:
    pdf_dir = Path(settings.data_pdf_path)
    if not pdf_dir.exists():
        raise HTTPException(status_code=404, detail=f"PDF directory not found: {pdf_dir}")

    parser = PDFParser()
    records = parser.parse_all_pdfs(str(pdf_dir))
    return _ingest_records(records, "pdf")


@app.post("/ingest/all")
async def ingest_all() -> dict[str, Any]:
    text_result = await ingest_text()
    pdf_result = await ingest_pdf()
    return {
        "text": text_result,
        "pdf": pdf_result,
        "total_parsed": text_result.get("parsed", 0) + pdf_result.get("parsed", 0),
        "total_published": text_result.get("published", 0) + pdf_result.get("published", 0),
    }


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="DeadMile Load Ingestion CLI")
    parser.add_argument("--ingest-all", action="store_true", help="Ingest all load files")
    parser.add_argument("--ingest-text", action="store_true", help="Ingest text files only")
    parser.add_argument("--ingest-pdf", action="store_true", help="Ingest PDF files only")
    args = parser.parse_args()

    if args.ingest_text or args.ingest_all:
        text_parser = TextParser()
        records = text_parser.parse_all_files(settings.data_text_path)
        result = _ingest_records(records, "text")
        print(f"Text: {result}")

    if args.ingest_pdf or args.ingest_all:
        pdf_parser = PDFParser()
        records = pdf_parser.parse_all_pdfs(settings.data_pdf_path)
        result = _ingest_records(records, "pdf")
        print(f"PDF: {result}")


if __name__ == "__main__":
    run_cli()
