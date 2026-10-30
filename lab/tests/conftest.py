"""Shared test fixtures. All tiny, all offline. Values are fixtures, not results."""

import json
import math
from pathlib import Path

import pytest

from dmlab.data.amazon import build_instance, stream_select
from dmlab.data.solomon import load_solomon
from dmlab.routing.model import Depot, Fleet, ProblemInstance, Stop, Units

FIXTURES = Path(__file__).parent / "fixtures"
TINY_SOLOMON = FIXTURES / "tiny_solomon.txt"
TINY_AMAZON = FIXTURES / "tiny_amazon"
BOSTON_ROUTE = "RouteID_00000000-0000-0000-0000-00000000000a"
CHICAGO_BAD_ROUTE = "RouteID_00000000-0000-0000-0000-00000000000b"

TEST_UNITS = Units(
    distance_unit="unit",
    distance_scale=1,
    time_unit="unit",
    time_scale=1,
    demand_unit="unit",
    time_is_hours=False,
    distance_label="test fixture",
    time_label="test fixture",
)


def make_instance(
    stops: list[Stop],
    depot_xy: tuple[float, float] = (0, 0),
    depot_tw: tuple[int, int] = (0, 1000),
    vehicles: int = 2,
    capacity: int = 10,
    max_shift: int = 1000,
) -> ProblemInstance:
    pts = [depot_xy] + [(s.x, s.y) for s in stops]
    m = [[int(math.dist(a, b)) for b in pts] for a in pts]
    return ProblemInstance(
        name="TEST",
        source="fixture",
        slice="fixture",
        depot=Depot(
            id="depot", x=depot_xy[0], y=depot_xy[1], tw_early=depot_tw[0], tw_late=depot_tw[1]
        ),
        stops=stops,
        fleet=Fleet(num_vehicles=vehicles, capacity=capacity, max_shift=max_shift),
        distance=m,
        duration=m,
        units=TEST_UNITS,
        data_version="fixture",
    )


def stop(
    sid: str,
    x: float,
    y: float = 0,
    delivery: int = 0,
    pickup: int = 0,
    service: int = 0,
    tw: tuple[int, int] = (0, 1000),
) -> Stop:
    return Stop(
        id=sid,
        kind="pickup" if pickup else "delivery",
        x=x,
        y=y,
        delivery=delivery,
        pickup=pickup,
        service=service,
        tw_early=tw[0],
        tw_late=tw[1],
    )


@pytest.fixture
def tiny_solomon() -> ProblemInstance:
    return load_solomon(TINY_SOLOMON, source="fixture")


@pytest.fixture
def mixed_instance() -> ProblemInstance:
    """Deliveries and pickups around a depot; load order matters (capacity 10)."""
    stops = [
        stop("d1", 10, 0, delivery=6, service=2),
        stop("d2", 0, 12, delivery=4, service=2),
        stop("d3", -9, 3, delivery=5, service=2, tw=(20, 200)),
        stop("p1", 12, 4, pickup=6, service=3),
        stop("p2", 2, 14, pickup=5, service=3),
        stop("p3", -11, -2, pickup=4, service=3, tw=(0, 150)),
    ]
    return make_instance(stops, vehicles=3, capacity=10, max_shift=300, depot_tw=(0, 400))


def _chunks(path: Path, n: int = 5):
    data = path.read_bytes()
    return (data[i : i + n] for i in range(0, len(data), n))


@pytest.fixture
def amazon_parts() -> dict:
    route_data = json.loads((TINY_AMAZON / "route_data.json").read_text())
    keep = {BOSTON_ROUTE, CHICAGO_BAD_ROUTE}
    return {
        "route_data": route_data,
        "packages": stream_select(_chunks(TINY_AMAZON / "package_data.json"), keep),
        "travel": stream_select(_chunks(TINY_AMAZON / "travel_times.json"), keep),
    }


@pytest.fixture
def tiny_amazon(amazon_parts: dict) -> ProblemInstance:
    rid = BOSTON_ROUTE
    inst, problems = build_instance(
        rid,
        amazon_parts["route_data"][rid],
        amazon_parts["packages"][rid],
        amazon_parts["travel"][rid],
        "Boston",
        vans=2,
        shift_hours=10,
        data_version="fixture",
    )
    assert inst is not None, problems
    return inst
