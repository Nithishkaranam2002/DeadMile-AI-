"""K-Means market clustering."""

from __future__ import annotations

import asyncpg
import numpy as np
import structlog
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from shared import constants as c
from shared.geocoding import geocode_city
from shared.models import MarketCluster

logger = structlog.get_logger(__name__)


class MarketClusterer:
    async def cluster_markets(self, pool: asyncpg.Pool) -> list[MarketCluster]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH outbound AS (
                    SELECT origin_city AS city, origin_state AS state,
                           COUNT(*) AS outbound_count,
                           AVG(rate_per_mile) AS avg_outbound_rate,
                           AVG(miles) AS avg_distance,
                           COUNT(DISTINCT equipment) AS equip_diversity
                    FROM loads GROUP BY origin_city, origin_state
                ),
                inbound AS (
                    SELECT dest_city AS city, dest_state AS state,
                           COUNT(*) AS inbound_count,
                           AVG(rate_per_mile) AS avg_inbound_rate
                    FROM loads GROUP BY dest_city, dest_state
                )
                SELECT
                    COALESCE(o.city, i.city) AS city,
                    COALESCE(o.state, i.state) AS state,
                    COALESCE(o.avg_outbound_rate, 0) AS avg_outbound_rate,
                    COALESCE(i.avg_inbound_rate, 0) AS avg_inbound_rate,
                    COALESCE(o.outbound_count, 0) + COALESCE(i.inbound_count, 0) AS total_volume,
                    COALESCE(o.equip_diversity, 1) AS equip_diversity,
                    COALESCE(o.avg_distance, 500) AS avg_distance,
                    COALESCE(o.outbound_count, 0)::float / GREATEST(COALESCE(i.inbound_count, 0), 1) AS lane_balance
                FROM outbound o
                FULL OUTER JOIN inbound i ON o.city = i.city AND o.state = i.state
                WHERE COALESCE(o.city, i.city) IS NOT NULL
                """
            )

        if len(rows) < 5:
            return []

        features_list = []
        cities = []
        for r in rows:
            features_list.append([
                float(r["avg_outbound_rate"]),
                float(r["avg_inbound_rate"]),
                float(r["total_volume"]),
                float(r["equip_diversity"]),
                float(r["avg_distance"]),
                float(r["lane_balance"]),
            ])
            cities.append((r["city"], r["state"], dict(r)))

        x = np.array(features_list)
        scaler = StandardScaler()
        x_scaled = scaler.fit_transform(x)

        k = min(5, len(rows))
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(x_scaled)

        cluster_profiles = self._assign_cluster_labels(kmeans, x, labels, k)

        results: list[MarketCluster] = []
        for i, (city, state, raw) in enumerate(cities):
            lat, lng = geocode_city(city, state)
            cid = int(labels[i])
            results.append(
                MarketCluster(
                    city=city,
                    state=state,
                    lat=lat,
                    lng=lng,
                    cluster_id=cid,
                    cluster_label=cluster_profiles.get(cid, "Underserved"),
                    features={
                        "avg_outbound_rate": round(raw["avg_outbound_rate"], 2),
                        "avg_inbound_rate": round(raw["avg_inbound_rate"], 2),
                        "total_volume": int(raw["total_volume"]),
                        "equip_diversity": int(raw["equip_diversity"]),
                        "avg_distance": round(float(raw["avg_distance"]), 1),
                        "lane_balance": round(float(raw["lane_balance"]), 2),
                    },
                )
            )

        logger.info("markets_clustered", cities=len(results), clusters=k)
        return results

    def _assign_cluster_labels(
        self, kmeans: KMeans, x: np.ndarray, labels: np.ndarray, k: int
    ) -> dict[int, str]:
        """Map cluster IDs to human-readable labels based on centroid characteristics."""
        profiles: dict[int, str] = {}
        for cid in range(k):
            mask = labels == cid
            if not np.any(mask):
                profiles[cid] = c.CLUSTER_LABELS.get(cid, "Underserved")
                continue
            cluster_data = x[mask]
            avg_vol = cluster_data[:, 2].mean()
            avg_balance = cluster_data[:, 5].mean()
            avg_rate = cluster_data[:, 0].mean()
            avg_equip = cluster_data[:, 3].mean()

            if avg_vol > np.median(x[:, 2]) and 0.5 < avg_balance < 2.0:
                profiles[cid] = "Mega Hub"
            elif avg_balance > 1.5:
                profiles[cid] = "Origin Heavy"
            elif avg_balance < 0.7:
                profiles[cid] = "Destination Heavy"
            elif avg_equip < 2 and avg_rate > np.median(x[:, 0]):
                profiles[cid] = "Specialty"
            else:
                profiles[cid] = "Underserved"

        for cid in range(k):
            profiles.setdefault(cid, c.CLUSTER_LABELS.get(cid, "Underserved"))
        return profiles
