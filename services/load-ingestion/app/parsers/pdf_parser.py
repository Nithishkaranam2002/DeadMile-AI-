"""PDF broker sheet parser using pdfplumber."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pdfplumber
import structlog

from shared.models import LoadRecord

logger = structlog.get_logger(__name__)

CITY_STATE = re.compile(r"^(?P<city>[A-Za-z .'-]+),\s*(?P<state>[A-Z]{2})$")
EQUIPMENT_MAP = {
    "DV": "Dry Van",
    "DRY VAN": "Dry Van",
    "VAN": "Dry Van",
    "FB": "Flatbed",
    "FLATBED": "Flatbed",
    "RF": "Reefer",
    "REEFER": "Reefer",
    "SD": "Step Deck",
    "STEP DECK": "Step Deck",
    "STEP": "Step Deck",
}


def _clean_cell(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _parse_city_state(location: str) -> tuple[str, str]:
    location = _clean_cell(location)
    match = CITY_STATE.match(location)
    if match:
        return match.group("city").strip(), match.group("state").upper()
    parts = location.rsplit(",", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip().upper()[:2]
    raise ValueError(f"Cannot parse location: {location!r}")


def _parse_equipment(equip: str) -> str:
    key = _clean_cell(equip).upper()
    return EQUIPMENT_MAP.get(key, _clean_cell(equip).title())


def _parse_int(value: str) -> int:
    return int(re.sub(r"[^\d]", "", value or "0") or "0")


def _parse_float(value: str) -> float:
    cleaned = re.sub(r"[^\d.]", "", value or "0")
    return float(cleaned or "0")


def _parse_date(value: str) -> datetime | None:
    value = _clean_cell(value)
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _normalize_header(header: list[str | None]) -> list[str]:
    return [_clean_cell(h).lower().replace("$", "").replace("/", "") for h in header]


def _find_column(headers: list[str], *candidates: str, exact_only: bool = False) -> int | None:
    if exact_only:
        for candidate in candidates:
            for i, h in enumerate(headers):
                if h == candidate:
                    return i
        return None
    for candidate in candidates:
        for i, h in enumerate(headers):
            if h == candidate:
                return i
    for candidate in candidates:
        for i, h in enumerate(headers):
            if candidate in h and h != "miles":
                return i
    return None


class PDFParser:
    """Parser for broker load sheet PDFs."""

    def _row_to_load(self, row: list[str | None], headers: list[str]) -> LoadRecord | None:
        cells = [_clean_cell(c) for c in row]
        if not any(cells):
            return None

        col = {
            "load_id": _find_column(headers, "load id", "load_id", "id"),
            "origin": _find_column(headers, "origin"),
            "destination": _find_column(headers, "destination", "dest"),
            "equip": _find_column(headers, "equip", "equipment"),
            "pu_date": _find_column(headers, "pu date", "pickup", "pu"),
            "miles": _find_column(headers, "miles", "mile"),
            "weight": _find_column(headers, "weight", "wt"),
            "rate": _find_column(headers, "rate"),
            "rpm": _find_column(headers, "mi", "rpm", "per mi", exact_only=True),
            "req": _find_column(headers, "req", "requirement"),
        }

        def get(key: str) -> str:
            idx = col[key]
            if idx is None or idx >= len(cells):
                return ""
            return cells[idx]

        load_id = get("load_id")
        if not load_id or not load_id.upper().startswith("L-"):
            return None

        try:
            origin_city, origin_state = _parse_city_state(get("origin"))
            dest_city, dest_state = _parse_city_state(get("destination"))
        except ValueError as exc:
            logger.warning("pdf_row_location_parse_failed", load_id=load_id, error=str(exc))
            return None

        miles = _parse_int(get("miles"))
        rate = _parse_float(get("rate"))
        rpm_raw = get("rpm")
        rpm = _parse_float(rpm_raw) if rpm_raw else (round(rate / miles, 2) if miles else 0.0)

        req = get("req")
        requirements = None if not req or req.lower() == "none" else req

        return LoadRecord(
            load_id=load_id.upper() if not load_id.startswith("L-") else load_id,
            origin_city=origin_city,
            origin_state=origin_state,
            dest_city=dest_city,
            dest_state=dest_state,
            pickup_start=_parse_date(get("pu_date")),
            equipment=_parse_equipment(get("equip")),
            commodity="General freight",
            weight_lbs=_parse_int(get("weight")),
            miles=miles,
            rate=rate,
            rate_per_mile=rpm,
            requirements=requirements,
            source="pdf",
            format_type="pdf",
        )

    def parse_pdf(self, filepath: str) -> list[LoadRecord]:
        path = Path(filepath)
        records: list[LoadRecord] = []

        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()
                if not tables:
                    continue
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    headers = _normalize_header(table[0])
                    for row in table[1:]:
                        try:
                            record = self._row_to_load(row, headers)
                            if record:
                                records.append(record)
                        except Exception as exc:
                            logger.warning(
                                "pdf_row_parse_failed",
                                file=path.name,
                                page=page_num,
                                error=str(exc),
                            )
        logger.info("pdf_parsed", file=path.name, count=len(records))
        return records

    def parse_all_pdfs(self, directory: str) -> list[LoadRecord]:
        dir_path = Path(directory)
        if not dir_path.exists():
            logger.warning("pdf_directory_not_found", directory=directory)
            return []

        all_records: list[LoadRecord] = []
        for filepath in sorted(dir_path.glob("*.pdf")):
            all_records.extend(self.parse_pdf(str(filepath)))
        return all_records
