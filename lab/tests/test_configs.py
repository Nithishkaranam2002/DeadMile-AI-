from pathlib import Path

import pytest
import yaml

CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs"


@pytest.mark.parametrize("name", ["suites", "gates", "budgets", "business"])
def test_config_parses(name: str) -> None:
    data = yaml.safe_load((CONFIG_DIR / f"{name}.yaml").read_text())
    assert isinstance(data, dict) and data


def test_business_costs_are_labeled_assumptions() -> None:
    data = yaml.safe_load((CONFIG_DIR / "business.yaml").read_text())
    assert data["label"] == "assumption"
