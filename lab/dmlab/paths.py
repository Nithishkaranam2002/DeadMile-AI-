"""Lab paths and config loading."""

from pathlib import Path
from typing import Any

import yaml

LAB_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = LAB_DIR / "configs"


def load_config(name: str) -> dict[str, Any]:
    return yaml.safe_load((CONFIG_DIR / f"{name}.yaml").read_text())


def datasets_config() -> dict[str, Any]:
    return load_config("datasets")
