"""Qdrant vector store for semantic load search."""

from __future__ import annotations

import os
from typing import Any, Optional

import asyncpg
import structlog

logger = structlog.get_logger(__name__)

COLLECTION_NAME = "load_commodities"
VECTOR_SIZE = 384


class QdrantSeeder:
    """Seeds and searches load commodity embeddings."""

    def __init__(self) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self._Distance = Distance
        self._VectorParams = VectorParams
        self.client = QdrantClient(
            host=os.getenv("QDRANT_HOST", "qdrant"),
            port=int(os.getenv("QDRANT_PORT", "6333")),
        )
        self.collection_name = os.getenv("QDRANT_COLLECTION", COLLECTION_NAME)
        self._model = None

    @property
    def model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception as exc:
                logger.warning("sentence_transformer_unavailable", error=str(exc))
        return self._model

    def _ensure_collection(self) -> None:
        from qdrant_client.models import Distance, VectorParams

        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in collections:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )

    async def seed(self, pool: asyncpg.Pool) -> int:
        if self.model is None:
            logger.warning("qdrant_seed_skipped_no_model")
            return 0

        self._ensure_collection()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT load_id, commodity, equipment, origin_city, origin_state,
                       dest_city, dest_state, weight_lbs, rate, miles,
                       ST_Y(origin_point::geometry) AS lat,
                       ST_X(origin_point::geometry) AS lng
                FROM loads
                """
            )

        from qdrant_client.models import PointStruct

        points = []
        for i, row in enumerate(rows):
            text = (
                f"{row['commodity']} {row['equipment']} from {row['origin_city']} {row['origin_state']} "
                f"to {row['dest_city']} {row['dest_state']} {row['weight_lbs']} lbs"
            )
            vector = self.model.encode(text).tolist()
            points.append(
                PointStruct(
                    id=i + 1,
                    vector=vector,
                    payload={
                        "load_id": row["load_id"],
                        "commodity": row["commodity"],
                        "equipment": row["equipment"],
                        "origin": f"{row['origin_city']}, {row['origin_state']}",
                        "destination": f"{row['dest_city']}, {row['dest_state']}",
                        "rate": float(row["rate"]),
                        "miles": row["miles"],
                        "lat": float(row["lat"]) if row["lat"] else None,
                        "lng": float(row["lng"]) if row["lng"] else None,
                    },
                )
            )

        if points:
            self.client.upsert(collection_name=self.collection_name, points=points)
        logger.info("qdrant_seeded", points=len(points))
        return len(points)

    async def search(
        self,
        query: str,
        limit: int = 10,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
    ) -> list[dict[str, Any]]:
        if self.model is None:
            return []

        try:
            self._ensure_collection()
        except Exception:
            return []

        query_vector = self.model.encode(query).tolist()
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit,
        )

        hits = []
        for r in results:
            payload = r.payload or {}
            if lat is not None and lng is not None and payload.get("lat") and payload.get("lng"):
                from app.geo import haversine_miles

                dist = haversine_miles(lat, lng, payload["lat"], payload["lng"])
                if dist > 300:
                    continue
            hits.append({**payload, "score": r.score})
        return hits
