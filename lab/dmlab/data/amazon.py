"""Amazon Last Mile Routing Research Challenge 2021 (evaluation set) loader.

Data: CC BY-NC 4.0 (non-commercial). One Amazon route = one instance.

Fields used
* route_data: the stop with type "Station" is the depot; "Dropoff" stops are
  delivery stops; station_code gives the city slice; date + departure_time_utc
  is time zero; executor_capacity_cm3 is the van capacity.
* package_data: per stop, the sum of package volumes (depth x height x width,
  cm3) is the demand, the sum of planned_service_time_seconds is the service
  time, and the intersection of the packages' time windows (UTC) is the stop's
  window. Missing windows (NaN) mean open.
* travel_times: directed stop to stop seconds, rounded to whole seconds, as the
  duration matrix.
* Distance: haversine on lat/lng, in whole meters. Straight line, so it
  underestimates road distance; labeled as such.

Assumptions (configs/datasets.yaml, labeled as assumptions): 2 identical vans
per route with the route's capacity, and a 10 h shift from departure that is
also the planning horizon. Windows are clipped to [0, horizon].

The package data file writes missing windows as the bare token NaN, which is
not valid JSON. ``NaNToNull`` rewrites that token to null in the byte stream
before ijson parses it. This is safe for this dataset: NaN never occurs inside
a key or string (stop ids are two uppercase letters, route and package ids are
lowercase hex, times are digits).
"""

import hashlib
import json
import math
import random
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ijson

from dmlab.routing.model import Depot, Fleet, ProblemInstance, Stop, Units

EARTH_RADIUS_M = 6_371_008.8  # mean Earth radius
TIME_FMT = "%Y-%m-%d %H:%M:%S"

AMAZON_UNITS = Units(
    distance_unit="km",
    distance_scale=1000,  # internal meters
    time_unit="hour",
    time_scale=3600,  # internal seconds
    demand_unit="cm3",
    time_is_hours=True,
    distance_label="haversine straight-line km on stop coordinates (not road distance)",
    time_label="Amazon travel times (seconds) plus planned service time",
)


class NaNToNull:
    """File-like wrapper that turns the bare JSON token NaN into null."""

    def __init__(self, chunks: Iterable[bytes]) -> None:
        self._it: Iterator[bytes] = iter(chunks)
        self._carry = b""

    def read(self, n: int = -1) -> bytes:
        if n == 0:  # ijson probes the stream type with read(0); consume nothing
            return b""
        for chunk in self._it:
            data = (self._carry + chunk).replace(b"NaN", b"null")
            # Keep 2 bytes back: a NaN split across chunks ends in "N" or "Na".
            out, self._carry = data[:-2], data[-2:]
            if out:
                return out
        out, self._carry = self._carry, b""
        return out


def city_of(station_code: str, cities: dict[str, list[str]]) -> str | None:
    for city, prefixes in cities.items():
        if any(station_code.startswith(p) for p in prefixes):
            return city
    return None


def candidate_order(
    route_data: dict[str, Any], cities: dict[str, list[str]], seed: int
) -> dict[str, list[str]]:
    """Route ids per city: sorted, then shuffled with a fixed seed."""
    out: dict[str, list[str]] = {c: [] for c in cities}
    for rid in sorted(route_data):
        city = city_of(route_data[rid]["station_code"], cities)
        if city:
            out[city].append(rid)
    for city in out:
        random.Random(f"{seed}:{city}").shuffle(out[city])
    return out


def stream_select(source: Iterable[bytes], keep: set[str]) -> dict[str, Any]:
    """Stream a top level {route_id: value} JSON file, keeping only some routes."""
    found: dict[str, Any] = {}
    for rid, value in ijson.kvitems(NaNToNull(source), "", use_float=True):
        if rid in keep:
            found[rid] = value
            if len(found) == len(keep):
                break
    return found


def _ts(value: str | None) -> datetime | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return datetime.strptime(value, TIME_FMT).replace(tzinfo=UTC)


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def build_instance(
    route_id: str,
    route: dict[str, Any],
    packages: dict[str, Any],
    travel: dict[str, Any],
    city: str,
    vans: int,
    shift_hours: float,
    data_version: str,
) -> tuple[ProblemInstance | None, list[str]]:
    """Return (instance, problems). The instance is None if any problem is found.

    Problems are data checks done before any solver runs; a route with a
    problem is excluded from the subset with the reason recorded.
    """
    problems: list[str] = []
    horizon = int(shift_hours * 3600)
    stations = [sid for sid, s in route["stops"].items() if s["type"] == "Station"]
    if len(stations) != 1:
        return None, [f"expected one Station stop, found {len(stations)}"]
    depot_id = stations[0]
    stop_ids = sorted(sid for sid in route["stops"] if sid != depot_id)
    t0 = datetime.strptime(
        f"{route['date_YYYY_MM_DD']} {route['departure_time_utc']}", TIME_FMT
    ).replace(tzinfo=UTC)

    node_ids = [depot_id, *stop_ids]
    for sid in node_ids:
        if sid not in travel or any(o not in travel[sid] for o in node_ids):
            problems.append(f"travel times missing for stop {sid}")
            break
    if problems:
        return None, problems
    dur = [[int(round(float(travel[a][b]))) if a != b else 0 for b in node_ids] for a in node_ids]

    stops: list[Stop] = []
    for idx, sid in enumerate(stop_ids, start=1):
        s = route["stops"][sid]
        pk = packages.get(sid)
        if not pk:
            problems.append(f"no packages for stop {sid}")
            continue
        volume = 0.0
        service = 0.0
        early, late = 0, horizon
        for p in pk.values():
            d = p["dimensions"]
            volume += float(d["depth_cm"]) * float(d["height_cm"]) * float(d["width_cm"])
            service += float(p["planned_service_time_seconds"])
            start = _ts(p["time_window"]["start_time_utc"])
            end = _ts(p["time_window"]["end_time_utc"])
            if start is not None:
                early = max(early, int((start - t0).total_seconds()))
            if end is not None:
                late = min(late, int((end - t0).total_seconds()))
        early = min(max(early, 0), horizon)
        if late < early:
            problems.append(f"stop {sid}: empty or past time window")
            continue
        if dur[0][idx] > late:
            problems.append(f"stop {sid}: window closes before a van can arrive")
            continue
        stops.append(
            Stop(
                id=sid,
                kind="delivery",
                x=float(s["lng"]),
                y=float(s["lat"]),
                delivery=int(math.ceil(volume)),
                pickup=0,
                service=int(round(service)),
                tw_early=early,
                tw_late=late,
            )
        )
    if problems:
        return None, problems

    capacity = int(math.floor(float(route["executor_capacity_cm3"])))
    total = sum(s.delivery for s in stops)
    if total > vans * capacity:
        return None, [f"total volume {total} cm3 exceeds {vans} vans x {capacity} cm3"]

    coords = [(route["stops"][sid]["lat"], route["stops"][sid]["lng"]) for sid in node_ids]
    dist = [
        [0 if i == j else int(round(haversine_m(a, b))) for j, b in enumerate(coords)]
        for i, a in enumerate(coords)
    ]
    depot_stop = route["stops"][depot_id]
    inst = ProblemInstance(
        name=route_id.removeprefix("RouteID_"),
        source="amazon",
        slice=city,
        depot=Depot(
            id=depot_id,
            x=float(depot_stop["lng"]),
            y=float(depot_stop["lat"]),
            tw_early=0,
            tw_late=horizon,
        ),
        stops=stops,
        fleet=Fleet(num_vehicles=vans, capacity=capacity, max_shift=horizon),
        distance=dist,
        duration=dur,
        units=AMAZON_UNITS,
        data_version=data_version,
        labels=[
            "Amazon Last Mile 2021 evaluation set (CC BY-NC 4.0)",
            "distance: haversine straight-line, not road distance",
            f"assumption: {vans} vans per route, {shift_hours:g} h shift",
        ],
        metadata={
            "route_id": route_id,
            "station_code": route["station_code"],
            "date": route["date_YYYY_MM_DD"],
            "departure_time_utc": route["departure_time_utc"],
            "stops_with_time_window": sum(
                1 for s in stops if s.tw_early > 0 or s.tw_late < horizon
            ),
        },
    )
    return inst, []


def write_processed(path: Path, route_id: str, city: str, route: Any, pk: Any, tt: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"route_id": route_id, "city": city, "route": route, "packages": pk, "travel": tt}
    path.write_text(json.dumps(payload, sort_keys=True))


def load_amazon(path: Path, vans: int, shift_hours: float) -> ProblemInstance:
    raw = path.read_bytes()
    d = json.loads(raw)
    inst, problems = build_instance(
        d["route_id"],
        d["route"],
        d["packages"],
        d["travel"],
        d["city"],
        vans,
        shift_hours,
        "sha256:" + hashlib.sha256(raw).hexdigest(),
    )
    if inst is None:
        raise ValueError(f"{path.name}: {'; '.join(problems)}")
    return inst
