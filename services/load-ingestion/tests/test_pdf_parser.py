"""Unit tests for PDF parser header/row parsing."""

from app.parsers.pdf_parser import PDFParser, _parse_city_state, _parse_equipment


def test_parse_city_state() -> None:
    city, state = _parse_city_state("Atlanta, GA")
    assert city == "Atlanta"
    assert state == "GA"

    city, state = _parse_city_state("Salt Lake City, UT")
    assert city == "Salt Lake City"
    assert state == "UT"


def test_parse_equipment_aliases() -> None:
    assert _parse_equipment("DV") == "Dry Van"
    assert _parse_equipment("FB") == "Flatbed"
    assert _parse_equipment("Reefer") == "Reefer"


def test_row_to_load_from_table_row() -> None:
    parser = PDFParser()
    headers = ["load id", "origin", "destination", "equip", "pu date", "miles", "weight", "rate", "mi", "req"]
    row = ["L-0000100", "Chicago, IL", "Miami, FL", "DV", "2026-06-20", "1200", "42000", "2800", "2.33", ""]
    load = parser._row_to_load(row, headers)
    assert load is not None
    assert load.load_id == "L-0000100"
    assert load.origin_city == "Chicago"
    assert load.dest_city == "Miami"
    assert load.equipment == "Dry Van"
    assert load.miles == 1200
    assert load.rate == 2800.0
    assert load.requirements is None
    assert load.source == "pdf"
