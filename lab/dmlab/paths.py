"""Lab paths and config loading."""

import os
from pathlib import Path
from typing import Any

import yaml

LAB_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = LAB_DIR / "configs"


def load_config(name: str) -> dict[str, Any]:
    return yaml.safe_load((CONFIG_DIR / f"{name}.yaml").read_text())


def datasets_config() -> dict[str, Any]:
    return load_config("datasets")


# Optional override of configs/budgets.yaml (for example very low budgets to
# test that the agent stops cleanly). An environment variable, so worker
# processes started by the runner read the same file.
BUDGETS_ENV = "DMLAB_BUDGETS_FILE"


def budgets_path(root: Path = LAB_DIR) -> Path:
    override = os.environ.get(BUDGETS_ENV)
    return Path(override) if override else root / "configs" / "budgets.yaml"


def budgets_config(root: Path = LAB_DIR) -> dict[str, Any]:
    path = budgets_path(root)
    return yaml.safe_load(path.read_text()) if path.exists() else {}
