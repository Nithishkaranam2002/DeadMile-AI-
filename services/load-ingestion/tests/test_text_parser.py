"""Unit tests for text load parser."""

from datetime import datetime

import pytest

from app.parsers.text_parser import TextParser

VERBOSE_BLOCK = """LOAD L-0000001
  Origin......: Atlanta, GA 30303  (33.749, -84.388)
  Destination.: Fort Worth, TX 76102  (32.7555, -97.3308)
  Pickup......: 2026-06-15 13:00 to 2026-06-15 16:00
  Delivery....: 2026-06-17 14:00 to 2026-06-17 18:00
  Equipment...: Dry Van
  Commodity...: Packaged food / 37,500 lbs
  Miles.......: 908
  Rate........: $1,700  ($1.87/mi)
  Requirements: None"""

REFERENCE_BLOCK = """=== Load Ref L-0000002 ===
PU: Knoxville, TN 37902 | 2026-06-18 10:00 - 2026-06-18 13:00
DEL: Toledo, OH 43604 | 2026-06-19 07:00 - 2026-06-19 13:00
Equip Flatbed; 518 mi; 43,100# Lumber
Pay $1,350 @ $2.61/mile
Notes: None"""

COMPACT_BLOCK = """L-0000009 | Los Angeles,CA -> Oakland,CA
  pu 2026-06-15 06:00  del 2026-06-16 13:00
  Dry Van 398mi wt 20700 comm=Consumer goods
  rate $1,025 rpm 2.58 req[None]"""


@pytest.fixture
def parser() -> TextParser:
    return TextParser()


class TestFormatDetection:
    def test_detect_verbose(self, parser: TextParser) -> None:
        assert parser.detect_format(VERBOSE_BLOCK) == "verbose"

    def test_detect_reference(self, parser: TextParser) -> None:
        assert parser.detect_format(REFERENCE_BLOCK) == "reference"

    def test_detect_compact(self, parser: TextParser) -> None:
        assert parser.detect_format(COMPACT_BLOCK) == "compact"


class TestVerboseParser:
    def test_parse_verbose_load(self, parser: TextParser) -> None:
        load = parser.parse_verbose(VERBOSE_BLOCK)
        assert load.load_id == "L-0000001"
        assert load.origin_city == "Atlanta"
        assert load.origin_state == "GA"
        assert load.origin_zip == "30303"
        assert load.origin_lat == pytest.approx(33.749)
        assert load.origin_lng == pytest.approx(-84.388)
        assert load.dest_city == "Fort Worth"
        assert load.dest_state == "TX"
        assert load.equipment == "Dry Van"
        assert load.commodity == "Packaged food"
        assert load.weight_lbs == 37500
        assert load.miles == 908
        assert load.rate == pytest.approx(1700.0)
        assert load.rate_per_mile == pytest.approx(1.87)
        assert load.requirements is None
        assert load.pickup_start == datetime(2026, 6, 15, 13, 0)


class TestReferenceParser:
    def test_parse_reference_load(self, parser: TextParser) -> None:
        load = parser.parse_reference(REFERENCE_BLOCK)
        assert load.load_id == "L-0000002"
        assert load.origin_city == "Knoxville"
        assert load.origin_state == "TN"
        assert load.dest_city == "Toledo"
        assert load.dest_state == "OH"
        assert load.equipment == "Flatbed"
        assert load.commodity == "Lumber"
        assert load.weight_lbs == 43100
        assert load.miles == 518
        assert load.rate == pytest.approx(1350.0)
        assert load.rate_per_mile == pytest.approx(2.61)
        assert load.origin_lat is None
        assert load.pickup_start == datetime(2026, 6, 18, 10, 0)


class TestCompactParser:
    def test_parse_compact_load(self, parser: TextParser) -> None:
        load = parser.parse_compact(COMPACT_BLOCK)
        assert load.load_id == "L-0000009"
        assert load.origin_city == "Los Angeles"
        assert load.origin_state == "CA"
        assert load.dest_city == "Oakland"
        assert load.dest_state == "CA"
        assert load.equipment == "Dry Van"
        assert load.commodity == "Consumer goods"
        assert load.weight_lbs == 20700
        assert load.miles == 398
        assert load.rate == pytest.approx(1025.0)
        assert load.rate_per_mile == pytest.approx(2.58)
        assert load.requirements is None


class TestMixedFile:
    def test_parse_mixed_file(self, parser: TextParser, tmp_path) -> None:
        fixture = tmp_path / "mixed.txt"
        fixture.write_text(
            VERBOSE_BLOCK + "\n\n" + REFERENCE_BLOCK + "\n\n" + COMPACT_BLOCK
        )
        loads = parser.parse_file(str(fixture))
        assert len(loads) == 3
        assert {load.load_id for load in loads} == {"L-0000001", "L-0000002", "L-0000009"}
        assert {load.format_type for load in loads} == {"verbose", "reference", "compact"}


class TestEdgeCases:
    def test_hazmat_requirement(self, parser: TextParser) -> None:
        block = COMPACT_BLOCK.replace("req[None]", "req[Hazmat]")
        load = parser.parse_compact(block)
        assert load.requirements == "Hazmat"

    def test_multi_word_city(self, parser: TextParser) -> None:
        block = VERBOSE_BLOCK.replace("Fort Worth", "Salt Lake City").replace("TX 76102", "UT 84101")
        load = parser.parse_verbose(block)
        assert load.dest_city == "Salt Lake City"
        assert load.dest_state == "UT"
