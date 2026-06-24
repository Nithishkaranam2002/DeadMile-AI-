"""Parse pasted load board text or screenshots and rank by profitability."""

from __future__ import annotations

import base64
import csv
import io
import json
import logging
import math
import re
import uuid
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app.carrier_context import get_cost_overrides
from app.config import settings
from app.db import get_pool
from app.import_history_db import get_import_history, list_import_history, save_import_history
from app.proxy import proxy_json
from shared.geocoding import geocode_city

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/import", tags=["import"])

PARSE_SYSTEM_PROMPT = """You parse freight load board text into structured JSON.
Return a JSON object with key "loads" containing an array of loads.
Each load must have: origin_city, origin_state, dest_city, dest_state, miles (integer),
rate (number, total dollars), equipment (string), commodity (string, optional),
weight_lbs (integer, optional), pickup_date (string, optional).
Normalize state to 2-letter abbreviation. Infer equipment from context when missing.
Return ONLY valid JSON, no markdown."""

VISION_SYSTEM_PROMPT = """Extract all freight loads from this load board screenshot.
Return JSON object with key "loads": array of objects with origin_city, origin_state,
dest_city, dest_state, miles, rate, equipment, commodity, pickup_date.
Return ONLY valid JSON."""


class ImportRequest(BaseModel):
    raw_text: str = Field(..., min_length=10)
    driver_lat: float
    driver_lng: float
    equipment: str = "Dry Van"


class CompareTextRequest(BaseModel):
    load_a_text: str = Field(..., min_length=5)
    load_b_text: str = Field(..., min_length=5)
    driver_lat: float
    driver_lng: float
    equipment: str = "Dry Van"


class ImportAnalyzeResponse(BaseModel):
    loads: list[dict[str, Any]]
    parsed_count: int
    insight: str
    winner_load_id: Optional[str] = None
    location_warning: Optional[str] = None
    pickup_cities: list[str] = Field(default_factory=list)
    nearest_pickup_miles: Optional[float] = None


class CsvImportRequest(BaseModel):
    csv_text: str = Field(..., min_length=5)
    driver_lat: float
    driver_lng: float
    equipment: str = "Dry Van"


class SaveHistoryRequest(BaseModel):
    driver_city: Optional[str] = None
    driver_state: Optional[str] = None
    equipment: str = "Dry Van"
    parsed_count: int = 0
    insight: str = ""
    loads: list[dict[str, Any]]
    raw_preview: Optional[str] = None


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def _location_context(
    driver_lat: float, driver_lng: float, parsed: list[dict[str, Any]]
) -> tuple[Optional[str], list[str], Optional[float]]:
    cities: set[str] = set()
    min_dist: Optional[float] = None
    for load in parsed:
        olat, olng = geocode_city(load["origin_city"], load["origin_state"])
        cities.add(f"{load['origin_city']}, {load['origin_state']}")
        dist = _haversine_miles(driver_lat, driver_lng, olat, olng)
        if min_dist is None or dist < min_dist:
            min_dist = dist
    warning = None
    if min_dist is not None and min_dist > 150:
        pickup_list = ", ".join(sorted(cities)[:3])
        warning = (
            f"Your location is ~{min_dist:.0f} mi from the nearest pickup ({pickup_list}). "
            "Deadhead to pickup is included in profit — make sure your location is where the truck actually is."
        )
    return warning, sorted(cities), min_dist


_CSV_ORIGIN_KEYS = ("origin", "origin_city", "pickup", "from", "o_city")
_CSV_DEST_KEYS = ("destination", "dest_city", "delivery", "to", "d_city")
_CSV_RATE_KEYS = ("rate", "price", "pay", "amount", "gross")
_CSV_MILES_KEYS = ("miles", "distance", "mi", "loaded_miles")


def _csv_field(row: dict[str, str], keys: tuple[str, ...]) -> str:
    lower_map = {k.lower().strip(): v for k, v in row.items()}
    for key in keys:
        if key in lower_map and lower_map[key].strip():
            return lower_map[key].strip()
    return ""


def _parse_city_state(value: str) -> tuple[str, str]:
    if "," in value:
        parts = value.split(",", 1)
        return parts[0].strip(), parts[1].strip().upper()[:2]
    return value.strip(), "XX"


def _parse_csv(csv_text: str, default_equipment: str) -> list[dict[str, Any]]:
    loads: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        return loads
    for row in reader:
        origin_raw = _csv_field(row, _CSV_ORIGIN_KEYS)
        dest_raw = _csv_field(row, _CSV_DEST_KEYS)
        if not origin_raw or not dest_raw:
            continue
        origin_city, origin_state = _parse_city_state(origin_raw)
        dest_city, dest_state = _parse_city_state(dest_raw)
        miles_str = _csv_field(row, _CSV_MILES_KEYS).replace(",", "")
        rate_str = _csv_field(row, _CSV_RATE_KEYS).replace("$", "").replace(",", "")
        try:
            miles = int(float(miles_str)) if miles_str else 0
            rate = float(rate_str) if rate_str else 0.0
        except ValueError:
            continue
        if miles <= 0 or rate <= 0:
            continue
        equip = _csv_field(row, ("equipment", "equip", "trailer")) or default_equipment
        loads.append(
            {
                "origin_city": origin_city,
                "origin_state": origin_state,
                "dest_city": dest_city,
                "dest_state": dest_state,
                "miles": miles,
                "rate": rate,
                "equipment": equip,
                "commodity": _csv_field(row, ("commodity", "freight")) or "General freight",
            }
        )
    return loads


def _regex_parse(raw_text: str, default_equipment: str) -> list[dict[str, Any]]:
    """Fallback parser when OpenAI is unavailable."""
    loads: list[dict[str, Any]] = []
    pattern = re.compile(
        r"([A-Za-z\s\.]+),\s*([A-Z]{2})\s*[→\-–>]+?\s*([A-Za-z\s\.]+),\s*([A-Z]{2})"
        r".*?(?:(?:Dry Van|Reefer|Flatbed|Step Deck)[\s|]*)?"
        r".*?(\d[\d,]*)\s*mi.*?[\$]([\d,]+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    for i, match in enumerate(pattern.finditer(raw_text)):
        origin_city, origin_state, dest_city, dest_state, miles, rate = match.groups()
        loads.append(
            {
                "origin_city": origin_city.strip(),
                "origin_state": origin_state.upper(),
                "dest_city": dest_city.strip(),
                "dest_state": dest_state.upper(),
                "miles": int(miles.replace(",", "")),
                "rate": float(rate.replace(",", "")),
                "equipment": default_equipment,
                "commodity": "General freight",
            }
        )
        if i >= 19:
            break
    return loads


async def _openai_parse_text(raw_text: str) -> list[dict[str, Any]]:
    if not settings.openai_api_key:
        return []

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": PARSE_SYSTEM_PROMPT},
                {"role": "user", "content": raw_text[:12000]},
            ],
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        return data.get("loads", []) if isinstance(data, dict) else data
    except Exception as exc:
        logger.warning("OpenAI text parse failed: %s", exc)
        return []


async def _openai_parse_image(image_bytes: bytes, mime: str) -> list[dict[str, Any]]:
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OpenAI API key required for screenshot import")

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        b64 = base64.b64encode(image_bytes).decode()
        response = await client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all loads from this image."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                    ],
                },
            ],
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        return data.get("loads", []) if isinstance(data, dict) else data
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("OpenAI vision parse failed")
        raise HTTPException(status_code=502, detail=f"Screenshot parse failed: {exc}") from exc


def _normalize_parsed(raw_loads: list[dict[str, Any]], default_equipment: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in raw_loads:
        if not isinstance(item, dict):
            continue
        origin_city = str(item.get("origin_city", "")).strip()
        origin_state = str(item.get("origin_state", "")).strip().upper()[:2]
        dest_city = str(item.get("dest_city", "")).strip()
        dest_state = str(item.get("dest_state", "")).strip().upper()[:2]
        if not origin_city or not dest_city:
            continue
        miles = int(item.get("miles") or 0)
        rate = float(item.get("rate") or 0)
        if miles <= 0 or rate <= 0:
            continue
        normalized.append(
            {
                "origin_city": origin_city,
                "origin_state": origin_state or "XX",
                "dest_city": dest_city,
                "dest_state": dest_state or "XX",
                "miles": miles,
                "rate": rate,
                "equipment": str(item.get("equipment") or default_equipment),
                "commodity": str(item.get("commodity") or "General freight"),
                "weight_lbs": int(item.get("weight_lbs") or 40000),
                "pickup_date": item.get("pickup_date"),
            }
        )
    return normalized


async def _analyze_loads(
    parsed: list[dict[str, Any]],
    driver_lat: float,
    driver_lng: float,
    equipment: str,
    cost_overrides: dict[str, Any],
    request_id: Optional[str],
) -> ImportAnalyzeResponse:
    if not parsed:
        raise HTTPException(status_code=422, detail="No loads could be parsed from input")

    results: list[dict[str, Any]] = []

    for i, load in enumerate(parsed):
        load_id = f"IMPORT-{uuid.uuid4().hex[:8].upper()}"
        origin_lat, origin_lng = geocode_city(load["origin_city"], load["origin_state"])
        dest_lat, dest_lng = geocode_city(load["dest_city"], load["dest_state"])

        body = {
            "load_id": load_id,
            "origin_city": load["origin_city"],
            "origin_state": load["origin_state"],
            "origin_lat": origin_lat,
            "origin_lng": origin_lng,
            "dest_city": load["dest_city"],
            "dest_state": load["dest_state"],
            "dest_lat": dest_lat,
            "dest_lng": dest_lng,
            "miles": load["miles"],
            "rate": load["rate"],
            "equipment": load.get("equipment") or equipment,
            "commodity": load.get("commodity") or "General freight",
            "weight_lbs": load.get("weight_lbs") or 40000,
            "driver_lat": driver_lat,
            "driver_lng": driver_lng,
            "cost_overrides": cost_overrides or None,
        }

        try:
            profit = await proxy_json(
                "POST",
                f"{settings.profitability_engine_url}/calculate/ad-hoc",
                json_body=body,
                timeout=45.0,
                request_id=request_id,
            )
            results.append(profit)
        except Exception as exc:
            logger.warning("Profitability calc failed for %s: %s", load_id, exc)

    if not results:
        raise HTTPException(status_code=502, detail="Could not calculate profitability for parsed loads")

    results.sort(key=lambda x: x.get("composite_score", 0), reverse=True)
    insight = _build_insight(results)
    winner = results[0].get("load_id") if results else None
    warning, pickup_cities, nearest_mi = _location_context(driver_lat, driver_lng, parsed)

    return ImportAnalyzeResponse(
        loads=results,
        parsed_count=len(parsed),
        insight=insight,
        winner_load_id=winner,
        location_warning=warning,
        pickup_cities=pickup_cities,
        nearest_pickup_miles=nearest_mi,
    )


def _build_insight(results: list[dict[str, Any]]) -> str:
    if len(results) < 2:
        top = results[0]
        return (
            f"Load nets {top.get('net_profit', 0):.0f} after all costs. "
            f"Destination market: {top.get('destination_market_label', 'Unknown')}."
        )

    best = results[0]
    worst = results[-1]
    best_net = float(best.get("net_profit") or 0)
    worst_net = float(worst.get("net_profit") or 0)
    diff = best_net - worst_net
    best_gross = float(best.get("gross_rate") or 0)
    worst_gross = float(worst.get("gross_rate") or 0)
    gross_diff = worst_gross - best_gross

    best_dest = best.get("destination") or "best market"
    worst_dest = worst.get("destination") or "worst market"
    best_label = best.get("destination_market_label") or "Neutral"
    worst_label = worst.get("destination_market_label") or "Neutral"

    if diff > 0 and gross_diff > 0:
        return (
            f"Top load nets ${diff:.0f} MORE than the worst despite paying ${gross_diff:.0f} LESS gross. "
            f"{best_dest} is {best_label} while {worst_dest} is {worst_label} — "
            f"outbound freight availability drives your next deadhead."
        )
    if diff > 0:
        return (
            f"Top load nets ${diff:.0f} more than the bottom pick. "
            f"Market at {best_dest} ({best_label}) beats {worst_dest} ({worst_label})."
        )
    return "Loads rank closely — check deadhead miles and destination market scores."


async def _parse_and_analyze(
    raw_text: str,
    driver_lat: float,
    driver_lng: float,
    equipment: str,
    req: Request,
) -> ImportAnalyzeResponse:
    request_id = req.headers.get("X-Request-ID")
    cost_overrides = await get_cost_overrides(req)

    parsed_raw = await _openai_parse_text(raw_text)
    if not parsed_raw:
        parsed_raw = _regex_parse(raw_text, equipment)
    parsed = _normalize_parsed(parsed_raw, equipment)

    return await _analyze_loads(parsed, driver_lat, driver_lng, equipment, cost_overrides, request_id)


@router.post("/parse", response_model=ImportAnalyzeResponse)
async def parse_imported_loads(request: ImportRequest, req: Request) -> ImportAnalyzeResponse:
    """Parse pasted load board text and rank by true net profit."""
    return await _parse_and_analyze(
        request.raw_text,
        request.driver_lat,
        request.driver_lng,
        request.equipment,
        req,
    )


@router.post("/screenshot", response_model=ImportAnalyzeResponse)
async def parse_screenshot(
    req: Request,
    file: UploadFile = File(...),
    driver_lat: float = Form(...),
    driver_lng: float = Form(...),
    equipment: str = Form("Dry Van"),
) -> ImportAnalyzeResponse:
    """Extract loads from a load board screenshot via GPT-4o vision."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Upload a PNG or JPG screenshot")

    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 10MB")

    request_id = req.headers.get("X-Request-ID")
    cost_overrides = await get_cost_overrides(req)

    parsed_raw = await _openai_parse_image(image_bytes, file.content_type)
    parsed = _normalize_parsed(parsed_raw, equipment)

    return await _analyze_loads(parsed, driver_lat, driver_lng, equipment, cost_overrides, request_id)


@router.post("/compare", response_model=ImportAnalyzeResponse)
async def compare_two_loads(request: CompareTextRequest, req: Request) -> ImportAnalyzeResponse:
    """Public load showdown — compare two pasted loads."""
    request_id = req.headers.get("X-Request-ID")
    cost_overrides = await get_cost_overrides(req)

    combined = f"Load A:\n{request.load_a_text}\n\nLoad B:\n{request.load_b_text}"
    parsed_raw = await _openai_parse_text(combined)
    if not parsed_raw:
        for label, text in [("A", request.load_a_text), ("B", request.load_b_text)]:
            fallback = _regex_parse(text, request.equipment)
            for item in fallback:
                item["commodity"] = f"Load {label}"
                parsed_raw.append(item)

    parsed = _normalize_parsed(parsed_raw[:2], request.equipment)
    if len(parsed) < 2:
        single = _normalize_parsed(_regex_parse(request.load_a_text, request.equipment), request.equipment)
        double = _normalize_parsed(_regex_parse(request.load_b_text, request.equipment), request.equipment)
        parsed = (single[:1] + double[:1]) if single and double else parsed

    if len(parsed) < 2:
        raise HTTPException(status_code=422, detail="Could not parse two loads — try clearer format")

    return await _analyze_loads(parsed[:2], request.driver_lat, request.driver_lng, request.equipment, cost_overrides, request_id)


@router.post("/csv", response_model=ImportAnalyzeResponse)
async def parse_csv_import(request: CsvImportRequest, req: Request) -> ImportAnalyzeResponse:
    """Parse CSV load export and rank by true net profit."""
    request_id = req.headers.get("X-Request-ID")
    cost_overrides = await get_cost_overrides(req)
    parsed = _normalize_parsed(_parse_csv(request.csv_text, request.equipment), request.equipment)
    if not parsed:
        raise HTTPException(
            status_code=422,
            detail="No loads in CSV — use columns: origin, destination, miles, rate",
        )
    return await _analyze_loads(
        parsed, request.driver_lat, request.driver_lng, request.equipment, cost_overrides, request_id
    )


def _carrier_id(req: Request) -> str:
    return getattr(req.state, "carrier_id", None) or "default"


@router.post("/history")
async def save_history(body: SaveHistoryRequest, req: Request) -> dict[str, int]:
    pool = await get_pool()
    try:
        history_id = await save_import_history(
            pool,
            _carrier_id(req),
            body.driver_city,
            body.driver_state,
            body.equipment,
            body.parsed_count,
            body.insight,
            body.loads,
            body.raw_preview,
        )
        return {"id": history_id}
    except Exception as exc:
        if "import_history" in str(exc):
            raise HTTPException(status_code=503, detail="Run: make db-migrate-import") from exc
        raise


@router.get("/history")
async def list_history(req: Request, limit: int = 20) -> list[dict[str, Any]]:
    pool = await get_pool()
    try:
        return await list_import_history(pool, _carrier_id(req), limit)
    except Exception as exc:
        if "import_history" in str(exc):
            return []
        raise


@router.get("/history/{history_id}")
async def get_history_item(history_id: int, req: Request) -> dict[str, Any]:
    pool = await get_pool()
    try:
        item = await get_import_history(pool, _carrier_id(req), history_id)
    except Exception as exc:
        if "import_history" in str(exc):
            raise HTTPException(status_code=503, detail="Run: make db-migrate-import") from exc
        raise
    if not item:
        raise HTTPException(status_code=404, detail="Import not found")
    return item
