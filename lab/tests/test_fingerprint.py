"""The solver fingerprint changes exactly when a solve result could change.

Each test hashes a temporary copy of the lab (dmlab, configs, data/bks.csv),
edits one thing, and hashes again. The import guard proves that the solve
path never imports an excluded file or folder.
"""

import ast
import shutil
from pathlib import Path

import pytest

from dmlab.harness import fingerprint as fpm
from dmlab.harness.runners import SolverConfig, SolveTask
from dmlab.paths import LAB_DIR
from dmlab.routing.runner import InstanceRef

CONFIG = SolverConfig(solver="pyvrp")


@pytest.fixture
def lab_copy(tmp_path: Path) -> Path:
    root = tmp_path / "lab"
    shutil.copytree(LAB_DIR / "dmlab", root / "dmlab", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(LAB_DIR / "configs", root / "configs")
    (root / "data").mkdir()
    shutil.copy(LAB_DIR / "data/bks.csv", root / "data/bks.csv")
    (root / "README.md").write_text("lab readme\n")
    return root


def _fp(root: Path, config: SolverConfig = CONFIG) -> str:
    return fpm.fingerprint(config, root)[0]


def _append(path: Path, text: str = "\n# edited\n") -> None:
    path.write_text(path.read_text() + text)


def test_fingerprint_is_stable(lab_copy):
    assert _fp(lab_copy) == _fp(lab_copy)


@pytest.mark.parametrize(
    "rel",
    [
        "README.md",
        "dmlab/harness/report_card.py",
        "dmlab/harness/gate_preview.py",
        "dmlab/harness/compare.py",
        "dmlab/routing/summary.py",
        "dmlab/api/main.py",
        "dmlab/cli/harness.py",
        "dmlab/safeguards/test_split.py",
        "configs/gates.yaml",
        "configs/suites.yaml",
    ],
)
def test_changes_that_cannot_change_a_solve_keep_the_fingerprint(lab_copy, rel):
    before = _fp(lab_copy)
    _append(lab_copy / rel)
    assert _fp(lab_copy) == before


def test_new_file_in_an_excluded_folder_keeps_the_fingerprint(lab_copy):
    before = _fp(lab_copy)
    (lab_copy / "dmlab/agent/graph.py").write_text("x = 1\n")
    assert _fp(lab_copy) == before


def test_agent_and_llm_budgets_keep_the_fingerprint(lab_copy):
    before = _fp(lab_copy)
    path = lab_copy / "configs/budgets.yaml"
    text = path.read_text()
    text = text.replace("llm_max_usd: 1.00", "llm_max_usd: 5").replace(
        "max_variants: 8", "max_variants: 3"
    )
    path.write_text(text)
    assert "llm_max_usd: 5" in path.read_text() and "max_variants: 3" in path.read_text()
    assert _fp(lab_copy) == before


@pytest.mark.parametrize(
    "rel",
    [
        "dmlab/routing/pyvrp_solver.py",
        "dmlab/routing/feasibility.py",
        "dmlab/routing/metrics.py",
        "dmlab/data/solomon.py",
        "dmlab/harness/runners.py",
        "configs/datasets.yaml",
        "configs/amazon_subset.yaml",
        "configs/business.yaml",
        "data/bks.csv",
    ],
)
def test_changes_that_can_change_a_solve_change_the_fingerprint(lab_copy, rel):
    before = _fp(lab_copy)
    _append(lab_copy / rel)
    assert _fp(lab_copy) != before


def test_new_routing_file_changes_the_fingerprint(lab_copy):
    before = _fp(lab_copy)
    (lab_copy / "dmlab/routing/new_solver.py").write_text("x = 1\n")
    assert _fp(lab_copy) != before


def test_per_run_wall_clock_budget_changes_the_fingerprint(lab_copy):
    before = _fp(lab_copy)
    path = lab_copy / "configs/budgets.yaml"
    path.write_text(path.read_text().replace("wall_clock_seconds: 120", "wall_clock_seconds: 60"))
    assert "wall_clock_seconds: 60" in path.read_text()
    assert _fp(lab_copy) != before


def test_solver_library_version_changes_the_fingerprint(lab_copy, monkeypatch):
    before = _fp(lab_copy)
    real = fpm.library_versions()
    monkeypatch.setattr(fpm, "library_versions", lambda: real | {"pyvrp": "0.15.0"})
    assert _fp(lab_copy) != before


def test_python_version_and_cpu_change_the_fingerprint(lab_copy, monkeypatch):
    before = _fp(lab_copy)
    monkeypatch.setattr(fpm, "cpu_model", lambda: "Other CPU")
    assert _fp(lab_copy) != before
    monkeypatch.undo()
    monkeypatch.setattr(fpm.sys, "version", "3.12.99 (test)")
    assert _fp(lab_copy) != before


def test_solver_config_and_plugin_code_change_the_fingerprint(lab_copy):
    base = SolverConfig(solver="ortools")
    other = SolverConfig(solver="ortools", params={"first_solution_strategy": "SAVINGS"})
    assert _fp(lab_copy, base) != _fp(lab_copy, other)
    p1 = SolverConfig(solver="ortools", plugins={"init": "def build(i):\n    return []\n"})
    p2 = SolverConfig(solver="ortools", plugins={"init": "def build(i):\n    return [[1]]\n"})
    assert p1.key() != p2.key() != base.key()
    assert _fp(lab_copy, p1) != _fp(lab_copy, p2)
    assert "plugin init" in p1.label()


def test_plugin_configs_cannot_run_yet():
    cfg = SolverConfig(solver="ortools", plugins={"init": "x = 1\n"})
    with pytest.raises(ValueError):
        SolveTask(group="g", config=cfg, ref=InstanceRef("fixture", "x"), seed=1, time_limit_s=1)


def test_manifest_lists_what_is_hashed(lab_copy):
    m = fpm.manifest(CONFIG, lab_copy)
    assert "dmlab/routing/pyvrp_solver.py" in m["files"]
    assert "dmlab/harness/report_card.py" not in m["files"]
    assert not any(f.startswith("dmlab/agent/") for f in m["files"])
    assert m["budgets"] == {"per_run.wall_clock_seconds": 120}
    assert {"python", "platform", "cpu", "lib.pyvrp", "lib.ortools"} <= set(m["environment"])


# Import guard -----------------------------------------------------------------

SOLVE_PATH_ROOTS = ("dmlab/harness/runners.py", "dmlab/routing/runner.py")


def _module_file(module: str) -> Path | None:
    base = LAB_DIR / Path(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.exists():
            return candidate
    return None


def _imports(path: Path) -> set[str]:
    """Every dmlab module imported anywhere in a file, including inside functions."""
    out = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names if a.name.startswith("dmlab")}
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("dmlab"):
            out.add(node.module)
            out |= {f"{node.module}.{a.name}" for a in node.names}
    return out


def _reachable() -> set[str]:
    seen: set[str] = set()
    todo = [LAB_DIR / r for r in SOLVE_PATH_ROOTS]
    while todo:
        path = todo.pop()
        rel = path.relative_to(LAB_DIR).as_posix()
        if rel in seen:
            continue
        seen.add(rel)
        for module in _imports(path):
            parts = module.split(".")
            # Importing a module also runs every parent package's __init__.
            for i in range(1, len(parts) + 1):
                f = _module_file(".".join(parts[:i]))
                if f is not None:
                    todo.append(f)
    return seen


def test_solve_path_never_imports_excluded_code():
    reachable = _reachable()
    assert "dmlab/routing/pyvrp_solver.py" in reachable  # the guard sees the solvers
    assert "dmlab/routing/feasibility.py" in reachable
    excluded = sorted(r for r in reachable if fpm.is_excluded(r))
    assert excluded == [], f"solve path imports excluded code: {excluded}"


def test_excluded_lists_are_pinned():
    # Changing what is excluded must be a deliberate, reviewed change.
    assert {
        "dmlab/agent",
        "dmlab/safeguards",
        "dmlab/api",
        "dmlab/forecasting",
        "dmlab/sim",
    } == fpm.EXCLUDED_DIRS
    assert len(fpm.EXCLUDED_FILES) == 11
    for rel in fpm.EXCLUDED_FILES:
        assert (LAB_DIR / rel).exists(), rel
