"""Text load file parser supporting three mixed formats."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import structlog

from shared.models import LoadRecord

logger = structlog.get_logger(__name__)

VERBOSE_HEADER = re.compile(r"^LOAD\s+(L-\d+)", re.MULTILINE)
REFERENCE_HEADER = re.compile(r"^===\s*Load\s+Ref\s+(L-\d+)\s*===", re.MULTILINE | re.IGNORECASE)
COMPACT_HEADER = re.compile(r"^(L-\d+)\s*\|", re.MULTILINE)

ORIGIN_VERBOSE = re.compile(
    r"Origin\.+:\s*(?P<city>[A-Za-z .'-]+),\s*(?P<state>[A-Z]{2})\s*(?P<zip>\d{5})?"
    r"(?:\s*\(\s*(?P<lat>-?\d+\.?\d*)\s*,\s*(?P<lng>-?\d+\.?\d*)\s*\))?",
    re.IGNORECASE,
)
DEST_VERBOSE = re.compile(
    r"Destination\.+:\s*(?P<city>[A-Za-z .'-]+),\s*(?P<state>[A-Z]{2})\s*(?P<zip>\d{5})?"
    r"(?:\s*\(\s*(?P<lat>-?\d+\.?\d*)\s*,\s*(?P<lng>-?\d+\.?\d*)\s*\))?",
    re.IGNORECASE,
)
PICKUP_VERBOSE = re.compile(
    r"Pickup\.+:\s*(?P<start>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+to\s+(?P<end>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})",
    re.IGNORECASE,
)
DELIVERY_VERBOSE = re.compile(
    r"Delivery\.+:\s*(?P<start>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+to\s+(?P<end>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})",
    re.IGNORECASE,
)
EQUIPMENT_VERBOSE = re.compile(r"Equipment\.+:\s*(.+)", re.IGNORECASE)
COMMODITY_VERBOSE = re.compile(r"Commodity\.+:\s*(.+)", re.IGNORECASE)
MILES_VERBOSE = re.compile(r"Miles\.+:\s*([\d,]+)", re.IGNORECASE)
RATE_VERBOSE = re.compile(
    r"Rate\.+:\s*\$?([\d,]+(?:\.\d+)?)\s*(?:\(\s*\$?([\d.]+)\s*/?\s*mi\s*\))?",
    re.IGNORECASE,
)
REQUIREMENTS_VERBOSE = re.compile(r"Requirements:\s*(.+)", re.IGNORECASE)

PU_REFERENCE = re.compile(
    r"PU:\s*(?P<city>[A-Za-z .'-]+),\s*(?P<state>[A-Z]{2})\s*(?P<zip>\d{5})?"
    r"\s*\|\s*(?P<start>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s*-\s*(?P<end>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})",
    re.IGNORECASE,
)
DEL_REFERENCE = re.compile(
    r"DEL:\s*(?P<city>[A-Za-z .'-]+),\s*(?P<state>[A-Z]{2})\s*(?P<zip>\d{5})?"
    r"\s*\|\s*(?P<start>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s*-\s*(?P<end>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})",
    re.IGNORECASE,
)
EQUIP_REFERENCE = re.compile(
    r"Equip\s+(?P<equip>[A-Za-z ]+?);\s*(?P<miles>[\d,]+)\s*mi;\s*(?P<weight>[\d,#]+)\s*(?P<commodity>.+)",
    re.IGNORECASE,
)
PAY_REFERENCE = re.compile(
    r"Pay\s+\$?([\d,]+(?:\.\d+)?)\s*@\s*\$?([\d.]+)\s*/?\s*mile",
    re.IGNORECASE,
)
NOTES_REFERENCE = re.compile(r"Notes:\s*(.+)", re.IGNORECASE)

COMPACT_ROUTE = re.compile(
    r"^(?P<load_id>L-\d+)\s*\|\s*"
    r"(?P<origin_city>[A-Za-z .'-]+),\s*(?P<origin_state>[A-Z]{2})\s*"
    r"->\s*"
    r"(?P<dest_city>[A-Za-z .'-]+),\s*(?P<dest_state>[A-Z]{2})",
    re.IGNORECASE | re.MULTILINE,
)
COMPACT_DATES = re.compile(
    r"pu\s+(?P<pu>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+del\s+(?P<del>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})",
    re.IGNORECASE,
)
COMPACT_DETAILS = re.compile(
    r"(?P<equip>Dry Van|Flatbed|Reefer|Step Deck)\s+"
    r"(?P<miles>[\d,]+)\s*mi\s+"
    r"wt\s+(?P<weight>[\d,]+)\s+"
    r"comm=(?P<commodity>.+)",
    re.IGNORECASE,
)
COMPACT_RATE = re.compile(
    r"rate\s+\$?([\d,]+(?:\.\d+)?)\s+rpm\s+([\d.]+)",
    re.IGNORECASE,
)
COMPACT_REQ = re.compile(r"req\[(?P<req>[^\]]*)\]", re.IGNORECASE)

DT_FORMAT = "%Y-%m-%d %H:%M"


def _parse_int(value: str) -> int:
    return int(re.sub(r"[^\d]", "", value))


def _parse_float(value: str) -> float:
    return float(re.sub(r"[^\d.]", "", value))


def _parse_dt(value: str) -> datetime:
    return datetime.strptime(value.strip(), DT_FORMAT)


def _normalize_requirements(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if cleaned.lower() in ("none", "n/a", ""):
        return None
    return cleaned


def _parse_weight_and_commodity_verbose(commodity_line: str) -> tuple[str, int]:
    """Parse 'Packaged food / 37,500 lbs' or similar."""
    weight_match = re.search(r"([\d,]+)\s*(?:lbs|#)", commodity_line, re.IGNORECASE)
    if weight_match:
        weight = _parse_int(weight_match.group(1))
        commodity = re.sub(r"\s*/\s*[\d,]+\s*(?:lbs|#).*$", "", commodity_line, flags=re.IGNORECASE).strip()
        commodity = re.sub(r"\s*[\d,]+\s*(?:lbs|#).*$", "", commodity, flags=re.IGNORECASE).strip()
        return commodity or commodity_line.strip(), weight
    return commodity_line.strip(), 0


def _parse_weight_reference(weight_str: str) -> int:
    return _parse_int(weight_str.replace("#", ""))


class TextParser:
    """Parser for mixed-format text load files."""

    def detect_format(self, block: str) -> str:
        stripped = block.strip()
        if stripped.startswith("LOAD L-") or "Origin......:" in block:
            return "verbose"
        if stripped.startswith("===") or "=== Load Ref" in block:
            return "reference"
        if re.match(r"^L-\d+\s*\|", stripped):
            return "compact"
        raise ValueError(f"Unable to detect format for block: {stripped[:80]!r}")

    def parse_verbose(self, block: str) -> LoadRecord:
        load_match = VERBOSE_HEADER.search(block)
        if not load_match:
            raise ValueError("Missing LOAD header in verbose block")

        origin = ORIGIN_VERBOSE.search(block)
        dest = DEST_VERBOSE.search(block)
        pickup = PICKUP_VERBOSE.search(block)
        delivery = DELIVERY_VERBOSE.search(block)
        equipment = EQUIPMENT_VERBOSE.search(block)
        commodity_line = COMMODITY_VERBOSE.search(block)
        miles = MILES_VERBOSE.search(block)
        rate = RATE_VERBOSE.search(block)
        requirements = REQUIREMENTS_VERBOSE.search(block)

        if not all([origin, dest, equipment, commodity_line, miles, rate]):
            raise ValueError(f"Incomplete verbose block for {load_match.group(1)}")

        commodity, weight = _parse_weight_and_commodity_verbose(commodity_line.group(1).strip())
        total_rate = _parse_float(rate.group(1))
        rpm = _parse_float(rate.group(2)) if rate.group(2) else round(total_rate / _parse_int(miles.group(1)), 2)

        return LoadRecord(
            load_id=load_match.group(1),
            origin_city=origin.group("city").strip(),
            origin_state=origin.group("state").upper(),
            origin_zip=origin.group("zip"),
            origin_lat=float(origin.group("lat")) if origin.group("lat") else None,
            origin_lng=float(origin.group("lng")) if origin.group("lng") else None,
            dest_city=dest.group("city").strip(),
            dest_state=dest.group("state").upper(),
            dest_zip=dest.group("zip"),
            dest_lat=float(dest.group("lat")) if dest.group("lat") else None,
            dest_lng=float(dest.group("lng")) if dest.group("lng") else None,
            pickup_start=_parse_dt(pickup.group("start")) if pickup else None,
            pickup_end=_parse_dt(pickup.group("end")) if pickup else None,
            delivery_start=_parse_dt(delivery.group("start")) if delivery else None,
            delivery_end=_parse_dt(delivery.group("end")) if delivery else None,
            equipment=equipment.group(1).strip(),
            commodity=commodity,
            weight_lbs=weight,
            miles=_parse_int(miles.group(1)),
            rate=total_rate,
            rate_per_mile=rpm,
            requirements=_normalize_requirements(requirements.group(1) if requirements else None),
            source="text",
            format_type="verbose",
        )

    def parse_reference(self, block: str) -> LoadRecord:
        load_match = REFERENCE_HEADER.search(block)
        if not load_match:
            raise ValueError("Missing reference header")

        pu = PU_REFERENCE.search(block)
        del_line = DEL_REFERENCE.search(block)
        equip = EQUIP_REFERENCE.search(block)
        pay = PAY_REFERENCE.search(block)
        notes = NOTES_REFERENCE.search(block)

        if not all([pu, del_line, equip, pay]):
            raise ValueError(f"Incomplete reference block for {load_match.group(1)}")

        total_rate = _parse_float(pay.group(1))
        rpm = _parse_float(pay.group(2))
        miles = _parse_int(equip.group("miles"))

        return LoadRecord(
            load_id=load_match.group(1),
            origin_city=pu.group("city").strip(),
            origin_state=pu.group("state").upper(),
            origin_zip=pu.group("zip"),
            dest_city=del_line.group("city").strip(),
            dest_state=del_line.group("state").upper(),
            dest_zip=del_line.group("zip"),
            pickup_start=_parse_dt(pu.group("start")),
            pickup_end=_parse_dt(pu.group("end")),
            delivery_start=_parse_dt(del_line.group("start")),
            delivery_end=_parse_dt(del_line.group("end")),
            equipment=equip.group("equip").strip(),
            commodity=equip.group("commodity").strip(),
            weight_lbs=_parse_weight_reference(equip.group("weight")),
            miles=miles,
            rate=total_rate,
            rate_per_mile=rpm,
            requirements=_normalize_requirements(notes.group(1) if notes else None),
            source="text",
            format_type="reference",
        )

    def parse_compact(self, block: str) -> LoadRecord:
        route = COMPACT_ROUTE.search(block)
        dates = COMPACT_DATES.search(block)
        details = COMPACT_DETAILS.search(block)
        rate = COMPACT_RATE.search(block)
        req = COMPACT_REQ.search(block)

        if not all([route, details, rate]):
            raise ValueError(f"Incomplete compact block: {block[:80]!r}")

        total_rate = _parse_float(rate.group(1))
        rpm = _parse_float(rate.group(2))
        miles = _parse_int(details.group("miles"))

        return LoadRecord(
            load_id=route.group("load_id"),
            origin_city=route.group("origin_city").strip(),
            origin_state=route.group("origin_state").upper(),
            dest_city=route.group("dest_city").strip(),
            dest_state=route.group("dest_state").upper(),
            pickup_start=_parse_dt(dates.group("pu")) if dates else None,
            delivery_start=_parse_dt(dates.group("del")) if dates else None,
            equipment=details.group("equip").strip(),
            commodity=details.group("commodity").strip(),
            weight_lbs=_parse_int(details.group("weight")),
            miles=miles,
            rate=total_rate,
            rate_per_mile=rpm,
            requirements=_normalize_requirements(req.group("req") if req else None),
            source="text",
            format_type="compact",
        )

    def _split_blocks(self, content: str) -> list[str]:
        """Split file content into individual load blocks across all formats."""
        lines = content.strip()
        if not lines:
            return []

        boundaries: list[tuple[int, str]] = []
        for pattern, fmt in (
            (VERBOSE_HEADER, "verbose"),
            (REFERENCE_HEADER, "reference"),
            (COMPACT_HEADER, "compact"),
        ):
            for match in pattern.finditer(content):
                boundaries.append((match.start(), fmt))

        boundaries.sort(key=lambda x: x[0])
        if not boundaries:
            return []

        blocks: list[str] = []
        for i, (start, _) in enumerate(boundaries):
            end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(content)
            block = content[start:end].strip()
            if block:
                blocks.append(block)
        return blocks

    def parse_block(self, block: str) -> LoadRecord:
        fmt = self.detect_format(block)
        if fmt == "verbose":
            return self.parse_verbose(block)
        if fmt == "reference":
            return self.parse_reference(block)
        return self.parse_compact(block)

    def parse_file(self, filepath: str) -> list[LoadRecord]:
        path = Path(filepath)
        content = path.read_text(encoding="utf-8", errors="replace")
        records: list[LoadRecord] = []

        for block in self._split_blocks(content):
            try:
                records.append(self.parse_block(block))
            except Exception as exc:
                logger.warning("parse_block_failed", file=str(path), error=str(exc), block_preview=block[:120])
        return records

    def parse_all_files(self, directory: str) -> list[LoadRecord]:
        dir_path = Path(directory)
        if not dir_path.exists():
            logger.warning("directory_not_found", directory=directory)
            return []

        all_records: list[LoadRecord] = []
        for filepath in sorted(dir_path.glob("*.txt")):
            logger.info("parsing_text_file", file=filepath.name)
            all_records.extend(self.parse_file(str(filepath)))
        return all_records
