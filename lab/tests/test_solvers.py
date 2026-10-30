"""All three solvers on the tiny fixtures; every result goes through our checker."""

import pytest

from dmlab.routing.feasibility import check
from dmlab.routing.metrics import compute
from dmlab.routing.solver import get_solver

TIME_LIMIT = 1.0


@pytest.mark.parametrize("solver", ["pyvrp", "ortools", "nn"])
@pytest.mark.parametrize("fixture", ["tiny_solomon", "mixed_instance", "tiny_amazon"])
def test_solver_is_feasible(solver, fixture, request):
    inst = request.getfixturevalue(fixture)
    res = get_solver(solver).solve(inst, TIME_LIMIT, seed=1)
    assert res.found_solution, res.status
    report = check(inst, res.routes)
    assert report.feasible, report.violations
    assert sorted(n for r in res.routes for n in r) == list(range(1, inst.num_stops + 1))


def test_pyvrp_reported_distance_matches_checker(tiny_solomon):
    res = get_solver("pyvrp").solve(tiny_solomon, TIME_LIMIT, seed=1)
    rep = check(tiny_solomon, res.routes)
    assert sum(r.distance for r in rep.routes) == res.solver_reported["distance"]


def test_pyvrp_seeded_runs_repeat(mixed_instance):
    # Same seed, different short time limits still give feasible, comparable output.
    a = get_solver("pyvrp").solve(mixed_instance, 0.5, seed=3)
    b = get_solver("pyvrp").solve(mixed_instance, 0.5, seed=3)
    assert check(mixed_instance, a.routes).feasible and check(mixed_instance, b.routes).feasible


def test_nn_reports_unvisited_when_fleet_too_small(tiny_solomon):
    small = tiny_solomon.model_copy(
        update={"fleet": tiny_solomon.fleet.model_copy(update={"num_vehicles": 1})}
    )
    res = get_solver("nn").solve(small, TIME_LIMIT, seed=1)
    assert not res.found_solution and "unvisited" in res.status
    assert not check(small, res.routes).feasible


def test_seed_usage_flags():
    assert get_solver("pyvrp").uses_seed
    assert not get_solver("ortools").uses_seed and not get_solver("nn").uses_seed


def test_metrics_from_routes(tiny_solomon):
    res = get_solver("pyvrp").solve(tiny_solomon, TIME_LIMIT, seed=1)
    rep = check(tiny_solomon, res.routes)
    internal = sum(r.distance for r in rep.routes)
    m = compute(tiny_solomon, res.routes, rep, res.runtime_s, bks_distance_internal=internal)
    assert m.total_distance == internal / 10 and m.gap_to_bks_pct == 0.0
    assert m.productivity_name == "stops_per_100_time_units" and m.num_stops == 8
    assert m.cost_per_stop is None and "not computed" in m.cost_note
    assert m.total_distance_exact_euclidean is None  # only computed for Solomon sources
    as_solomon = tiny_solomon.model_copy(update={"source": "solomon"})
    m2 = compute(as_solomon, res.routes, rep, res.runtime_s)
    assert m2.total_distance_exact_euclidean >= m2.total_distance  # truncation shortens arcs

    # No gap for an infeasible solution.
    bad = check(tiny_solomon, res.routes[:-1])
    assert compute(tiny_solomon, res.routes[:-1], bad, 0.0, internal).gap_to_bks_pct is None


def test_cost_per_stop_uses_assumptions(tiny_amazon):
    res = get_solver("nn").solve(tiny_amazon, TIME_LIMIT, seed=1)
    rep = check(tiny_amazon, res.routes)
    unset = compute(tiny_amazon, res.routes, rep, 0.0, business={"cost_per_driver_hour": None})
    assert unset.cost_per_stop is None
    business = {"cost_per_driver_hour": 30.0, "cost_per_distance_unit": {"km": 1.0}}
    m = compute(tiny_amazon, res.routes, rep, 0.0, business=business)
    expected = (m.total_duration * 30.0 + m.total_distance * 1.0) / m.num_stops
    assert m.cost_per_stop == pytest.approx(expected) and m.cost_note.startswith("assumption")
    assert m.productivity_name == "stops_per_driver_hour"
