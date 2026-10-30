"""PyVRP search settings, formulation variants and the per run wall clock
budget. Tiny fixtures only. Values are fixtures, not results."""

from pathlib import Path

import pytest
from pyvrp.solve import SolveParams

from dmlab.harness.runners import WALL_CLOCK_ERROR, LocalRunner, SolverConfig, SolveTask
from dmlab.routing.formulation import Formulation, apply
from dmlab.routing.pyvrp_solver import build_solve_params
from dmlab.routing.runner import InstanceRef, run_task
from tests.conftest import TINY_SOLOMON

REF = InstanceRef("fixture", str(TINY_SOLOMON))


def test_empty_settings_are_pyvrp_defaults():
    assert build_solve_params({}) == SolveParams()


def test_settings_reach_solve_params():
    p = build_solve_params(
        {
            "ils": {"history_length": 50},
            "penalty": {"penalty_increase": 2.0},
            "neighbourhood": {"num_neighbours": 20},
            "perturbation": {"max_perturbations": 10},
            "operators": ["Relocate1", "Swap11"],
        }
    )
    assert p.ils.history_length == 50
    assert p.penalty.penalty_increase == 2.0
    assert p.neighbourhood.num_neighbours == 20
    assert p.perturbation.max_perturbations == 10
    assert [op.__name__ for op in p.operators] == ["Relocate1", "Swap11"]


@pytest.mark.parametrize(
    "bad",
    [
        {"history_length": 50},  # not in a section
        {"ils": {"population_size": 25}},  # PyVRP 0.14 has no population
        {"ils": {"history_length": 0}},  # PyVRP's own check
        {"operators": ["Crossover"]},
        {"operators": []},
    ],
)
def test_bad_settings_are_refused(bad):
    with pytest.raises(ValueError):
        build_solve_params(bad)


def test_time_limit_is_not_a_solver_setting():
    with pytest.raises(ValueError, match="fixed by the suite"):
        SolverConfig(solver="pyvrp", params={"time_limit_s": 60})


def test_formulation_tightens_a_copy(tiny_solomon):
    f = Formulation(
        tw_late_buffer_share=0.5,
        max_route_duration_factor=0.8,
        fleet_size_delta=-1,
        capacity_reserve_share=0.2,
    )
    seen = apply(tiny_solomon, f)
    assert seen.fleet.capacity == 40 and seen.fleet.num_vehicles == 2
    assert seen.fleet.max_shift == int(tiny_solomon.fleet.max_shift * 0.8)
    s0, t0 = tiny_solomon.stops[0], seen.stops[0]
    assert t0.tw_late == s0.tw_late - (s0.tw_late - s0.tw_early) // 2
    # The original is untouched.
    assert tiny_solomon.fleet.capacity == 50 and tiny_solomon.stops[0].tw_late == 1200


def test_formulation_bounds_only_allow_tightening():
    for bad in (
        {"max_route_duration_factor": 1.2},
        {"fleet_size_delta": 2},
        {"capacity_reserve_share": 0.9},
        {"something_else": 1},
    ):
        with pytest.raises(ValueError):
            Formulation(**bad)


def test_formulation_is_measured_on_the_original_instance():
    # Reserving 60% of capacity is out of bounds, so use the maximum (50%):
    # the solver sees capacity 25, the checker uses the real capacity 50.
    p = run_task("pyvrp", {}, REF, 1.0, 1, {"capacity_reserve_share": 0.5})
    assert p["formulation"]["capacity_reserve_share"] == 0.5
    assert p["instance"]["fleet"]["capacity"] == 50
    assert p["report"]["feasible"] is True


def test_formulation_is_part_of_the_config_key():
    base = SolverConfig(solver="pyvrp")
    other = SolverConfig(solver="pyvrp", formulation={"capacity_reserve_share": 0.1})
    assert base.key() != other.key()
    assert "formulation" in other.label()


def test_wall_clock_budget_stops_a_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    budgets = tmp_path / "budgets.yaml"
    budgets.write_text("per_run:\n  wall_clock_seconds: 0.5\n")
    monkeypatch.setenv("DMLAB_BUDGETS_FILE", str(budgets))
    task = SolveTask(
        group="candidate", config=SolverConfig(solver="pyvrp"), ref=REF, seed=1, time_limit_s=5
    )
    (out,) = list(LocalRunner(1).run([task]))
    assert out.payload is None
    assert WALL_CLOCK_ERROR in out.error
