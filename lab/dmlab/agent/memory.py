"""Experiment memory in the existing Qdrant.

After a variant is evaluated the agent stores its hypothesis, variant, result
and lesson; before proposing it retrieves similar past experiments. Only
quick (tune) and full validation results are stored. The agent never sees
test results, so none can be stored.

Embeddings: sentence-transformers/all-MiniLM-L6-v2 (384 dimensions, cosine),
loaded from the local HuggingFace cache with HF_HUB_OFFLINE=1 and a pinned
revision, so memory works offline and nothing is downloaded. The model name
and revision are stored on every point. Tests use ``HashEmbedder`` and
Qdrant's in-memory mode (no model, no server).

Written against qdrant-client 1.12.2 (matches the 1.12.5 server):
collection_exists, create_collection, upsert, query_points, scroll.
"""

import hashlib
import json
import os
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

COLLECTION = "lab_experiment_memory"
MINILM = "sentence-transformers/all-MiniLM-L6-v2"
# Snapshot in the local HuggingFace cache; pinned so embeddings never drift.
MINILM_REVISION = "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"
DIM = 384


class Embedder(ABC):
    name: str
    revision: str

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class MiniLMEmbedder(Embedder):
    name = MINILM
    revision = MINILM_REVISION

    def __init__(self) -> None:
        os.environ["HF_HUB_OFFLINE"] = "1"  # never download
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed; run `uv sync --group ml`"
            ) from exc
        self.model = SentenceTransformer(
            MINILM, revision=MINILM_REVISION, local_files_only=True, device="cpu"
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [list(map(float, v)) for v in vecs]


class HashEmbedder(Embedder):
    """Deterministic bag of words vectors, for tests only."""

    name = "test/hash-bag-of-words"
    revision = "1"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            v = np.zeros(DIM)
            for tok in text.lower().split():
                h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
                v[h % DIM] += 1.0
            n = np.linalg.norm(v)
            out.append(list(map(float, v / n if n else v)))
        return out


def memory_text(entry: dict[str, Any]) -> str:
    """What is embedded: the idea and what was learned, not raw numbers."""
    variant = entry.get("variant") or {}
    settings = {k: v for k, v in variant.items() if k not in {"hypothesis", "rationale", "name"}}
    return " | ".join(
        [
            f"kind {entry.get('kind')}",
            f"settings {json.dumps(settings, sort_keys=True)}",
            f"hypothesis {entry.get('hypothesis', '')}",
            f"outcome {entry.get('status', '')}",
            f"lesson {entry.get('lesson') or ''}",
        ]
    )


class ExperimentMemory:
    def __init__(self, client: QdrantClient, embedder: Embedder, collection: str = COLLECTION):
        self.client = client
        self.embedder = embedder
        self.collection = collection
        if not client.collection_exists(collection):
            client.create_collection(
                collection, vectors_config=VectorParams(size=DIM, distance=Distance.COSINE)
            )

    @classmethod
    def connect(cls, embedder: Embedder | None = None) -> "ExperimentMemory":
        # Not QDRANT_URL: the product's .env points that at the container name.
        url = os.environ.get("LAB_QDRANT_URL", "http://localhost:6333")
        return cls(QdrantClient(url=url, timeout=10), embedder or MiniLMEmbedder())

    def store(self, entry: dict[str, Any]) -> str:
        point_id = str(uuid.uuid4())
        payload = {
            **entry,
            "stored_at": datetime.now(UTC).isoformat(),
            "embedding_model": self.embedder.name,
            "embedding_revision": self.embedder.revision,
        }
        vec = self.embedder.embed([memory_text(entry)])[0]
        self.client.upsert(self.collection, [PointStruct(id=point_id, vector=vec, payload=payload)])
        return point_id

    def similar(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        vec = self.embedder.embed([query])[0]
        res = self.client.query_points(self.collection, query=vec, limit=limit, with_payload=True)
        return [{**p.payload, "similarity": round(float(p.score), 4)} for p in res.points]

    def find_config(self, config_key: str, champion_key: str) -> list[dict[str, Any]]:
        """Earlier experiments with exactly this solver config against this champion."""
        flt = Filter(
            must=[
                FieldCondition(key="config_key", match=MatchValue(value=config_key)),
                FieldCondition(key="champion_key", match=MatchValue(value=champion_key)),
            ]
        )
        points, _ = self.client.scroll(self.collection, scroll_filter=flt, limit=20)
        return [p.payload for p in points]

    def count(self) -> int:
        return self.client.count(self.collection).count
