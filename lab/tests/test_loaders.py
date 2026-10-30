"""Solomon and Amazon loaders on the tiny fixtures (no downloads)."""

import json

import pytest

from dmlab.data.amazon import NaNToNull, build_instance, candidate_order, haversine_m
from dmlab.data.solomon import dimacs_matrix, solomon_class
from dmlab.routing.model import Stop
from tests.conftest import BOSTON_ROUTE, CHICAGO_BAD_ROUTE, TINY_AMAZON


def test_solomon_fixture_scaling(tiny_solomon):
    inst = tiny_solomon
    assert inst.num_stops == 8 and inst.fleet.num_vehicles == 3 and inst.fleet.capacity == 50
    assert inst.depot.tw_late == 3000 and inst.fleet.max_shift == 3000  # 300 x 10
    s1 = inst.stops[0]
    assert (s1.delivery, s1.service, s1.tw_early, s1.tw_late) == (10, 100, 200, 1200)
    # depot (40,50) to customer 1 (45,68): sqrt(25 + 324) = 18.68... -> floor(186.8) = 186
    assert inst.distance[0][1] == 186 and inst.duration[0][1] == 186
    assert all(s.kind == "delivery" and s.pickup == 0 for s in inst.stops)
    assert inst.units.distance_scale == 10 and "not miles" in inst.units.distance_label


def test_dimacs_truncates():
    import numpy as np

    m = dimacs_matrix(np.array([[0, 0], [3, 4], [1, 1]]))
    assert m[0, 1] == 50  # exactly 5.0
    assert m[0, 2] == 14  # sqrt(2) = 1.414 -> 14


def test_solomon_class():
    assert [solomon_class(n) for n in ("C101", "c208", "R112", "RC105", "RC208")] == [
        "C1",
        "C2",
        "R1",
        "RC1",
        "RC2",
    ]


@pytest.mark.parametrize("chunk", [1, 2, 3, 4, 7, 64])
def test_nan_filter_across_chunk_boundaries(chunk):
    raw = (TINY_AMAZON / "package_data.json").read_bytes()
    expected = json.loads(raw.decode().replace("NaN", "null"))
    f = NaNToNull(raw[i : i + chunk] for i in range(0, len(raw), chunk))
    assert f.read(0) == b""  # ijson probes with read(0); nothing may be consumed
    out = b"".join(iter(lambda: f.read(65536), b""))
    assert json.loads(out) == expected


def test_amazon_fixture_instance(tiny_amazon):
    inst = tiny_amazon
    assert inst.source == "amazon" and inst.slice == "Boston"
    assert inst.depot.id == "ST" and inst.num_stops == 6
    assert inst.fleet.num_vehicles == 2 and inst.fleet.capacity == 400000
    assert inst.fleet.max_shift == 36000 and inst.depot.tw_late == 36000
    ac = next(s for s in inst.stops if s.id == "AC")
    # Two packages: one open, one 15:00-18:00 UTC; departure 14:00 UTC.
    assert (ac.tw_early, ac.tw_late) == (3600, 14400)
    assert ac.delivery == 30 * 20 * 11 + 30 * 20 * 11 and ac.service == 31 + 31
    # 0.01 degree of latitude is about 1112 m.
    assert inst.distance[0][1] == round(haversine_m((10.0, 20.0), (10.01, 19.995)))
    assert 1100 < haversine_m((10.0, 20.0), (10.01, 20.0)) < 1125
    assert inst.units.time_is_hours and "haversine" in inst.units.distance_label
    assert any("assumption" in label for label in inst.labels)


def test_amazon_contradictory_window_is_excluded(amazon_parts):
    rid = CHICAGO_BAD_ROUTE
    inst, problems = build_instance(
        rid,
        amazon_parts["route_data"][rid],
        amazon_parts["packages"][rid],
        amazon_parts["travel"][rid],
        "Chicago",
        2,
        10,
        "fixture",
    )
    assert inst is None and "empty or past time window" in problems[0]


def test_candidate_order_is_seeded_and_filtered(amazon_parts):
    cities = {"Boston": ["DBO"], "Chicago": ["DCH"]}
    a = candidate_order(amazon_parts["route_data"], cities, 7)
    assert a == candidate_order(amazon_parts["route_data"], cities, 7)
    assert a == {"Boston": [BOSTON_ROUTE], "Chicago": [CHICAGO_BAD_ROUTE]}  # DLA route dropped


def test_stop_kind_must_match_demand():
    with pytest.raises(ValueError):
        Stop(
            id="x",
            kind="delivery",
            x=0,
            y=0,
            delivery=1,
            pickup=2,
            service=0,
            tw_early=0,
            tw_late=1,
        )
