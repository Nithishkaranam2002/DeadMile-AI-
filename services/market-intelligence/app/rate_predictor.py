"""XGBoost lane rate predictor."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import asyncpg
import joblib
import numpy as np
import pandas as pd
import structlog
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBRegressor

from shared.models import RatePrediction

logger = structlog.get_logger(__name__)

MODEL_DIR = Path(__file__).parent / "models"
MODEL_PATH = MODEL_DIR / "rate_model.joblib"
META_PATH = MODEL_DIR / "rate_model_meta.json"


def _distance_bucket(miles: float) -> str:
    if miles < 300:
        return "short"
    if miles <= 800:
        return "medium"
    return "long"


def _weight_bucket(weight: int) -> str:
    if weight < 25000:
        return "light"
    if weight <= 40000:
        return "medium"
    return "heavy"


class RatePredictor:
    def __init__(self) -> None:
        self.model: Optional[XGBRegressor] = None
        self.encoders: dict[str, LabelEncoder] = {}
        self.feature_cols: list[str] = []
        self._load_model()

    def _load_model(self) -> None:
        if MODEL_PATH.exists():
            try:
                artifact = joblib.load(MODEL_PATH)
                self.model = artifact["model"]
                self.encoders = artifact["encoders"]
                self.feature_cols = artifact["feature_cols"]
                logger.info("rate_model_loaded")
            except Exception as exc:
                logger.warning("rate_model_load_failed", error=str(exc))

    async def _fetch_training_data(self, pool: asyncpg.Pool) -> pd.DataFrame:
        async with pool.acquire() as conn:
            history = await conn.fetch(
                """
                SELECT origin_city, origin_state, dest_city, dest_state,
                       equipment, avg_rate_per_mile, load_count, time
                FROM rate_history
                ORDER BY time DESC
                """
            )
            if history:
                return pd.DataFrame([dict(r) for r in history])

            loads = await conn.fetch(
                """
                SELECT origin_city, origin_state, dest_city, dest_state,
                       equipment, rate_per_mile, miles, weight_lbs, pickup_start
                FROM loads WHERE rate_per_mile > 0
                """
            )
        return pd.DataFrame([dict(r) for r in loads])

    def train(self, df: pd.DataFrame) -> dict:
        if df.empty:
            raise ValueError("No training data available")

        if "avg_rate_per_mile" in df.columns:
            df = df.rename(columns={"avg_rate_per_mile": "rate_per_mile"})
        if "miles" not in df.columns:
            df["miles"] = 500
        if "weight_lbs" not in df.columns:
            df["weight_lbs"] = 35000
        if "pickup_start" not in df.columns:
            df["pickup_start"] = datetime.now()

        df["origin_key"] = df["origin_city"] + ", " + df["origin_state"]
        df["dest_key"] = df["dest_city"] + ", " + df["dest_state"]
        df["day_of_week"] = pd.to_datetime(df["pickup_start"]).dt.dayofweek
        df["distance_bucket"] = df["miles"].apply(_distance_bucket)
        df["weight_bucket"] = df["weight_lbs"].apply(_weight_bucket)

        lane_avg = df.groupby(["origin_key", "dest_key", "equipment"])["rate_per_mile"].transform("mean")
        df["lane_historical_avg"] = lane_avg

        cat_cols = ["origin_key", "dest_key", "equipment", "distance_bucket", "weight_bucket"]
        for col in cat_cols:
            le = LabelEncoder()
            df[f"{col}_enc"] = le.fit_transform(df[col].astype(str))
            self.encoders[col] = le

        self.feature_cols = [f"{c}_enc" for c in cat_cols] + ["day_of_week", "lane_historical_avg", "miles"]
        x = df[self.feature_cols].values
        y = df["rate_per_mile"].values

        self.model = XGBRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            random_state=42,
        )
        self.model.fit(x, y)

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {"model": self.model, "encoders": self.encoders, "feature_cols": self.feature_cols},
            MODEL_PATH,
        )
        META_PATH.write_text(json.dumps({"trained_at": datetime.now().isoformat(), "samples": len(df)}))

        logger.info("rate_model_trained", samples=len(df))
        return {"samples": len(df), "features": len(self.feature_cols)}

    async def train_from_db(self, pool: asyncpg.Pool) -> dict:
        df = await self._fetch_training_data(pool)
        return self.train(df)

    def _encode(self, col: str, value: str) -> int:
        le = self.encoders.get(col)
        if le is None:
            return 0
        if value in le.classes_:
            return int(le.transform([value])[0])
        return 0

    async def _historical_avg(
        self, pool: asyncpg.Pool, origin: str, dest: str, equipment: str
    ) -> float:
        parts_o = origin.rsplit(", ", 1)
        parts_d = dest.rsplit(", ", 1)
        if len(parts_o) != 2 or len(parts_d) != 2:
            return 2.0
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT AVG(rate_per_mile) AS avg_rate
                FROM loads
                WHERE origin_city = $1 AND origin_state = $2
                  AND dest_city = $3 AND dest_state = $4
                  AND equipment = $5 AND rate_per_mile > 0
                """,
                parts_o[0], parts_o[1], parts_d[0], parts_d[1], equipment,
            )
            if row and row["avg_rate"]:
                return float(row["avg_rate"])
            row = await conn.fetchrow(
                "SELECT AVG(rate_per_mile) AS avg_rate FROM loads WHERE equipment = $1 AND rate_per_mile > 0",
                equipment,
            )
        return float(row["avg_rate"]) if row and row["avg_rate"] else 2.0

    async def predict(
        self,
        pool: asyncpg.Pool,
        origin_city: str,
        origin_state: str,
        dest_city: str,
        dest_state: str,
        equipment: str,
        days_ahead: int = 7,
        miles: int = 500,
        weight_lbs: int = 35000,
    ) -> RatePrediction:
        origin = f"{origin_city}, {origin_state}"
        destination = f"{dest_city}, {dest_state}"
        current_avg = await self._historical_avg(pool, origin, destination, equipment)

        if self.model is None:
            return RatePrediction(
                origin=origin,
                destination=destination,
                equipment=equipment,
                current_avg_rate=round(current_avg, 2),
                predicted_rate=round(current_avg, 2),
                confidence_low=round(current_avg * 0.9, 2),
                confidence_high=round(current_avg * 1.1, 2),
                trend="stable",
                trend_percent=0.0,
            )

        future_date = datetime.now() + timedelta(days=days_ahead)
        features = np.array([[
            self._encode("origin_key", origin),
            self._encode("dest_key", destination),
            self._encode("equipment", equipment),
            self._encode("distance_bucket", _distance_bucket(miles)),
            self._encode("weight_bucket", _weight_bucket(weight_lbs)),
            future_date.weekday(),
            current_avg,
            miles,
        ]])

        predicted = float(self.model.predict(features)[0])
        residual_std = max(0.15, current_avg * 0.08)
        trend_pct = ((predicted - current_avg) / current_avg * 100) if current_avg else 0
        if trend_pct > 3:
            trend = "rising"
        elif trend_pct < -3:
            trend = "falling"
        else:
            trend = "stable"

        return RatePrediction(
            origin=origin,
            destination=destination,
            equipment=equipment,
            current_avg_rate=round(current_avg, 2),
            predicted_rate=round(predicted, 2),
            confidence_low=round(predicted - 1.96 * residual_std, 2),
            confidence_high=round(predicted + 1.96 * residual_std, 2),
            trend=trend,
            trend_percent=round(trend_pct, 2),
        )
