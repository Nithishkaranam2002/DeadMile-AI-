"""Feasibility checker on a hand built line instance with known answers.

Depot at x=0, stop A at x=10 (delivery 5, service 2, window [0, 100]),
stop B at x=20 (delivery 4, service 3, window [50, 60]). Distance = duration.
Route [A, B] from time 0: A 10..12, B arrive 22, wait to 50, leave 53, back 73.
Departure can be pushed by 28 (all the waiting), so the duration is 45.
"""

from dmlab.routing.feasibility import check
from tests.conftest import make_instance, stop


def line(**overrides):
    a_tw = overrides.pop("a_tw", (0, 100))
    kw = {"capacity": 10, "vehicles": 2, "max_shift": 100, "depot_tw": (0, 200)} | overrides
    return make_instance(
        [
            stop("A", 10, delivery=5, service=2, tw=a_tw),
            stop("B", 20, delivery=4, service=3, tw=(50, 60)),
        ],
        **kw,
    )


def test_feasible_route_and_duration_push():
    rep = check(line(), [[1, 2]])
    assert rep.feasible and rep.violations == []
    r = rep.routes[0]
    assert (r.distance, r.end, r.departure, r.duration, r.wait) == (40, 73, 28, 45, 0)
    assert r.max_load == 9


def test_capacity_violation():
    rep = check(line(capacity=8), [[1, 2]])
    assert not rep.feasible and rep.counts == {"capacity": 1}
    assert rep.violations[0].amount == 1  # 9 loaded at departure, capacity 8


def test_time_window_violation():
    # B first: B 50..53, A arrive 63 but A closes at 30.
    rep = check(line(a_tw=(0, 30)), [[2, 1]])
    assert rep.counts == {"time_window": 1}
    assert rep.time_window_violations == 1 and rep.total_lateness == 33


def test_shift_length_violation():
    rep = check(line(max_shift=40), [[1, 2]])
    assert rep.counts == {"shift_length": 1} and rep.violations[0].amount == 5


def test_depot_return_violation():
    rep = check(line(depot_tw=(0, 70)), [[1, 2]])
    assert "depot_return" in rep.counts


def test_missing_duplicate_unknown_and_too_many_routes():
    inst = line(vehicles=1)
    assert check(inst, [[1]]).counts == {"missing_stop": 1}
    assert check(inst, [[1, 2, 1]]).counts.get("duplicate_stop") == 1
    assert check(inst, [[1, 2, 7]]).counts == {"unknown_node": 1}
    assert check(inst, [[1], [2]]).counts == {"too_many_routes": 1}


def test_pickup_load_order_matters(mixed_instance):
    # d1 (delivery 6) then p1 (pickup 6): 6 -> 0 -> 6. Reverse: 6 -> 12 > 10.
    d1, p1 = 1, 4
    others = [[2, 5], [3, 6]]
    assert "capacity" not in check(mixed_instance, [[d1, p1], *others]).counts
    assert check(mixed_instance, [[p1, d1], *others]).counts.get("capacity") == 1


def test_empty_routes_are_ignored():
    rep = check(line(), [[], [1, 2], []])
    assert rep.feasible and len(rep.routes) == 1
