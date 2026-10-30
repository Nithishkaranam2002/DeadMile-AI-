"""Experiment agent pieces: variant schemas, memory, LLM reply parsing,
redaction, the graph's Module 4 hook, and the static guarantee that the agent
cannot reach the test split. Offline; values are fixtures, not results."""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError
from qdrant_client import QdrantClient

from dmlab.agent.graph import build_graph
from dmlab.agent.llm import REDACTED, parse_json, redact
from dmlab.agent.memory import ExperimentMemory, HashEmbedder
from dmlab.agent.variants import (
    VARIANT_ADAPTER,
    CodeVariant,
    CodeVariantsDisabled,
    mentions_time_limit,
    to_solver_config,
)
from dmlab.harness.runners import SolverConfig
from dmlab.paths import LAB_DIR

BASE = {
    "name": "a variant",
    "hypothesis": "this change should help the search",
    "rationale": "because of a reason that is long enough",
    "expected_effect": "shorter distance",
}
CHAMP = SolverConfig(solver="pyvrp")


def test_parameter_variant_maps_to_solver_config():
    v = VARIANT_ADAPTER.validate_python(
        {
            **BASE,
            "kind": "parameter",
            "solver": "pyvrp",
            "pyvrp": {"penalty": {"penalty_increase": 2.0}, "operators": ["Relocate1", "Swap11"]},
        }
    )
    c = to_solver_config(v, CHAMP)
    assert c.params == {"penalty": {"penalty_increase": 2.0}, "operators": ["Relocate1", "Swap11"]}
    _ = c.uses_seed  # PyVRPSolver accepts the settings


def test_ortools_variant_uses_installed_enum_names():
    v = VARIANT_ADAPTER.validate_python(
        {
            **BASE,
            "kind": "parameter",
            "solver": "ortools",
            "ortools": {
                "first_solution_strategy": "SAVINGS",
                "local_search_metaheuristic": "TABU_SEARCH",
            },
        }
    )
    assert to_solver_config(v, CHAMP).solver == "ortools"


def test_formulation_variant_keeps_the_champion_solver():
    v = VARIANT_ADAPTER.validate_python(
        {**BASE, "kind": "formulation", "formulation": {"fleet_size_delta": -2}}
    )
    c = to_solver_config(v, CHAMP)
    assert c.solver == "pyvrp" and c.params == {} and c.formulation == {"fleet_size_delta": -2}


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "parameter", "solver": "pyvrp", "pyvrp": {}},  # changes nothing
        {"kind": "parameter", "solver": "pyvrp", "pyvrp": {"ils": {"population_size": 5}}},
        {"kind": "parameter", "solver": "nn", "pyvrp": {"ils": {"history_length": 5}}},
        {"kind": "parameter", "solver": "ortools", "pyvrp": {"ils": {"history_length": 5}}},
        {
            "kind": "parameter",
            "solver": "pyvrp",
            "pyvrp": {"perturbation": {"min_perturbations": 9, "max_perturbations": 3}},
        },
        {"kind": "formulation", "formulation": {}},
        {"kind": "formulation", "formulation": {"capacity_reserve_share": 0.9}},
        {
            "kind": "parameter",
            "solver": "pyvrp",
            "pyvrp": {"ils": {"history_length": 5}},
            "surprise": 1,
        },
    ],
)
def test_invalid_variants_are_rejected_not_repaired(bad):
    with pytest.raises(ValidationError):
        VARIANT_ADAPTER.validate_python({**BASE, **bad})


def test_code_variants_validate_but_cannot_become_a_config():
    v = VARIANT_ADAPTER.validate_python(
        {**BASE, "kind": "code", "plugin": "stop_clustering", "source": "def assign(): ..."}
    )
    assert isinstance(v, CodeVariant)
    with pytest.raises(CodeVariantsDisabled):
        to_solver_config(v, CHAMP)


def test_time_limit_is_spotted_anywhere():
    assert mentions_time_limit({"pyvrp": {"ils": {"time_limit_s": 9}}})
    assert mentions_time_limit({"max_runtime": 9})
    assert not mentions_time_limit({"pyvrp": {"ils": {"history_length": 9}}})


def test_memory_stores_and_retrieves():
    mem = ExperimentMemory(QdrantClient(":memory:"), HashEmbedder())
    mem.store(
        {
            "kind": "parameter",
            "hypothesis": "short history",
            "status": "not_better",
            "config_key": "k1",
            "champion_key": "c1",
            "lesson": "history 50 is too short",
        }
    )
    mem.store(
        {
            "kind": "formulation",
            "hypothesis": "reserve capacity",
            "status": "infeasible",
            "config_key": "k2",
            "champion_key": "c1",
        }
    )
    top = mem.similar("short history lesson", limit=1)[0]
    assert top["config_key"] == "k1" and top["embedding_model"] == HashEmbedder.name
    assert mem.find_config("k2", "c1") and not mem.find_config("k2", "other champion")


def test_parse_json_strips_only_wrappers():
    assert parse_json('<think>hmm</think>\n```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(ValueError):
        parse_json('{"a": 1,}')  # broken JSON is not repaired


def test_redact_removes_secret_env_values(monkeypatch):
    monkeypatch.setenv("SOME_SERVICE_TOKEN", "tok-1234567890")
    monkeypatch.setenv("HARMLESS_SETTING", "tok-not-secret")
    out = redact("a tok-1234567890 b tok-not-secret")
    assert out == f"a {REDACTED} b tok-not-secret"


def test_graph_has_a_slot_for_module_4_after_nominate():
    def gate(state, runtime):
        return {}

    edges = build_graph(tail=[("promotion_gate", gate)]).builder.edges
    assert ("nominate", "promotion_gate") in edges and ("promotion_gate", "finalize") in edges
    assert ("nominate", "finalize") in build_graph().builder.edges


AGENT_FILES = sorted((LAB_DIR / "dmlab/agent").rglob("*.py")) + [LAB_DIR / "dmlab/cli/agent.py"]
SPLIT_FUNCS = {"full_suite", "get_suite", "split_refs", "split_names", "_read_split"}


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.name)
def test_agent_code_cannot_reach_the_test_split(path: Path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "dmlab.safeguards.test_split"
            assert "test_split" not in (node.module or "")
            assert all(a.name not in {"test_split", "_read_split"} for a in node.names)
        if isinstance(node, ast.Import):
            assert all("test_split" not in a.name for a in node.names)
        if isinstance(node, ast.Attribute):
            assert node.attr != "_read_split"
        if isinstance(node, ast.Call):
            fn = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if fn in SPLIT_FUNCS:
                args = [*node.args, *(k.value for k in node.keywords)]
                assert args, f"{path.name}: {fn}() without an explicit split"
                for a in args:
                    assert isinstance(a, ast.Constant) and a.value in {"tune", "validation"}, (
                        f"{path.name}: {fn}() must name tune or validation literally"
                    )


def test_agent_suites_are_tune_and_validation():
    from dmlab.agent.evaluate import confirmation_suite, screening_suite

    try:
        quick, full = screening_suite(), confirmation_suite()
    except FileNotFoundError:
        pytest.skip("benchmark data not downloaded on this machine")
    assert quick.split == "tune" and full.split == "validation"
    assert quick.time_limit_s < full.time_limit_s
