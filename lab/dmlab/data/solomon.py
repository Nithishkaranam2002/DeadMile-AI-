"""Solomon VRPTW loader.

Parses the original Solomon text format with vrplib (2.2, checked in the
installed source: read_instance(path, instance_format="solomon") returns
vehicles, capacity, node_coord, demand, time_window, service_time and a float
euclidean edge_weight).

Scaling follows the DIMACS convention used by the distance only best known
solutions: integer distance = floor(10 * euclidean), the same rule as PyVRP's
own "dimacs" rounding. Travel time equals distance, and time windows and
service times are multiplied by 10. Display values are internal / 10, in
abstract Solomon units (not miles, not minutes).
"""

import hashlib
import re
from pathlib import Path

import numpy as np
import vrplib

from dmlab.routing.model import Depot, Fleet, ProblemInstance, Stop, Units

SCALE = 10
CLASSES = ("C1", "C2", "R1", "R2", "RC1", "RC2")

SOLOMON_UNITS = Units(
    distance_unit="Solomon unit (abstract)",
    distance_scale=SCALE,
    time_unit="Solomon time unit (abstract)",
    time_scale=SCALE,
    demand_unit="Solomon demand unit",
    time_is_hours=False,
    distance_label="benchmark: abstract distance units, not miles",
    time_label="benchmark: abstract time units, not hours",
)


def solomon_class(name: str) -> str:
    m = re.fullmatch(r"(RC|R|C)([12])\d\d", name.upper())
    if not m:
        raise ValueError(f"not a Solomon instance name: {name}")
    return f"{m.group(1)}{m.group(2)}"


def dimacs_matrix(coords: np.ndarray) -> np.ndarray:
    diff = coords[:, None, :].astype(float) - coords[None, :, :].astype(float)
    euclid = np.sqrt((diff**2).sum(axis=-1))
    return (SCALE * euclid).astype(np.int64)  # truncation, as in DIMACS / PyVRP "dimacs"


def load_solomon(path: Path, source: str = "solomon") -> ProblemInstance:
    raw = vrplib.read_instance(str(path), instance_format="solomon")
    name = str(raw["name"]).strip().upper()
    coords = np.asarray(raw["node_coord"])
    demand = np.asarray(raw["demand"])
    tw = np.asarray(raw["time_window"])
    service = np.asarray(raw["service_time"])
    matrix = dimacs_matrix(coords)

    depot = Depot(
        id="depot",
        x=float(coords[0, 0]),
        y=float(coords[0, 1]),
        tw_early=int(tw[0, 0]) * SCALE,
        tw_late=int(tw[0, 1]) * SCALE,
    )
    stops = [
        Stop(
            id=str(i),  # Solomon customer number
            kind="delivery",
            x=float(coords[i, 0]),
            y=float(coords[i, 1]),
            delivery=int(demand[i]),
            pickup=0,
            service=int(service[i]) * SCALE,
            tw_early=int(tw[i, 0]) * SCALE,
            tw_late=int(tw[i, 1]) * SCALE,
        )
        for i in range(1, len(coords))
    ]
    fleet = Fleet(
        num_vehicles=int(raw["vehicles"]),
        capacity=int(raw["capacity"]),
        max_shift=depot.tw_late - depot.tw_early,
    )
    is_fixture = source == "fixture"
    return ProblemInstance(
        name=name,
        source="fixture" if is_fixture else "solomon",
        slice="fixture" if is_fixture else solomon_class(name),
        depot=depot,
        stops=stops,
        fleet=fleet,
        distance=matrix.tolist(),
        duration=matrix.tolist(),
        units=SOLOMON_UNITS,
        data_version="sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        labels=["benchmark", "abstract distance units, not miles"],
        metadata={"file": path.name, "convention": "dimacs_trunc1 (floor(10*d))"},
    )


def list_instances(raw_dir: Path) -> list[Path]:
    return sorted(p for p in raw_dir.glob("*.txt") if p.is_file())
