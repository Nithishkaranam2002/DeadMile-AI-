"""Solver fingerprint: a hash of everything that can change a solve result.

Used as the reuse key for champion runs (with instance, seed, time limit,
data version and worker count), so a commit that only touches the report
card or a README does not force a full rerun.

Included (default include: anything new under dmlab is hashed automatically):
* every .py file under dmlab, except EXCLUDED_FILES and EXCLUDED_DIRS;
* configs/datasets.yaml, configs/amazon_subset.yaml, configs/business.yaml
  (cost per stop is logged on every solve run) and data/bks.csv (gap metric);
* from configs/budgets.yaml only the settings that can change one solve run
  (BUDGET_KEYS), not the agent and LLM budgets;
* the solver config key (solver, parameters and any plugin code);
* the Python version, the solver libraries' versions, the platform and the
  CPU model (time limited solvers get further on a faster CPU).

Excluded: files that only read, aggregate or present finished results, or
parse arguments into values that are already part of the reuse key, and whole
folders the solve path never imports. tests/test_fingerprint.py fails if the
solve path ever imports an excluded file or folder.
"""

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from dmlab.harness.runners import SolverConfig
from dmlab.paths import LAB_DIR

EXCLUDED_FILES = frozenset(
    {
        "dmlab/harness/report_card.py",
        "dmlab/harness/gate_preview.py",
        "dmlab/harness/compare.py",
        "dmlab/harness/stats.py",
        "dmlab/harness/selfcheck.py",
        "dmlab/harness/registry.py",
        "dmlab/routing/summary.py",
        "dmlab/api/main.py",
        "dmlab/cli/harness.py",
        "dmlab/cli/route.py",
        "dmlab/cli/data.py",
    }
)
EXCLUDED_DIRS = frozenset(
    {"dmlab/agent", "dmlab/safeguards", "dmlab/api", "dmlab/forecasting", "dmlab/sim"}
)
HASHED_FILES = (
    "configs/datasets.yaml",
    "configs/amazon_subset.yaml",
    "configs/business.yaml",
    "data/bks.csv",
)
# (section, key) paths in budgets.yaml that can change a single solve run.
BUDGET_KEYS = (("per_run", "wall_clock_seconds"),)
LIBRARIES = ("pyvrp", "ortools", "numpy", "vrplib", "pydantic", "pyyaml", "protobuf")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_excluded(rel: str) -> bool:
    return rel in EXCLUDED_FILES or any(rel.startswith(d + "/") for d in EXCLUDED_DIRS)


def code_files(root: Path = LAB_DIR) -> list[str]:
    """Hashed .py files, relative to the lab root, sorted."""
    rels = (p.relative_to(root).as_posix() for p in (root / "dmlab").rglob("*.py"))
    return sorted(r for r in rels if "__pycache__" not in r and not is_excluded(r))


def library_versions() -> dict[str, str]:
    out = {}
    for name in LIBRARIES:
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            out[name] = "not installed"
    return out


def cpu_model() -> str:
    try:
        if sys.platform == "darwin":
            return subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        if sys.platform.startswith("linux"):
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return platform.processor() or "unknown"


def environment() -> dict[str, str]:
    return {
        "python": sys.version,
        "platform": f"{sys.platform} {platform.machine()}",
        "cpu": cpu_model(),
        **{f"lib.{k}": v for k, v in library_versions().items()},
    }


def _budget_settings(root: Path) -> dict[str, Any]:
    path = root / "configs/budgets.yaml"
    data = yaml.safe_load(path.read_text()) if path.exists() else {}
    return {".".join(keys): (data.get(keys[0]) or {}).get(keys[1]) for keys in BUDGET_KEYS}


def manifest(config: SolverConfig, root: Path = LAB_DIR) -> dict[str, Any]:
    """Every hashed item with its hash or value; logged as fingerprint.json."""
    files = {}
    for rel in [*code_files(root), *HASHED_FILES]:
        path = root / rel
        files[rel] = _sha256(path.read_bytes()) if path.exists() else "missing"
    return {
        "solver_config": config.model_dump(),
        "config_key": config.key(),
        "files": files,
        "budgets": _budget_settings(root),
        "environment": environment(),
        "excluded_files": sorted(EXCLUDED_FILES),
        "excluded_dirs": sorted(EXCLUDED_DIRS),
    }


def fingerprint(config: SolverConfig, root: Path = LAB_DIR) -> tuple[str, dict[str, Any]]:
    m = manifest(config, root)
    hashed = {k: m[k] for k in ("config_key", "files", "budgets", "environment")}
    return _sha256(json.dumps(hashed, sort_keys=True).encode())[:16], m
