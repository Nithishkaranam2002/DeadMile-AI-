"""The committed splits are frozen, stratified, disjoint and reproducible."""

from collections import Counter
from pathlib import Path

import pytest
import yaml

from dmlab.data.solomon import solomon_class
from dmlab.harness import splits

SUITES = yaml.safe_load((Path(__file__).parents[1] / "configs/suites.yaml").read_text())
COMMITTED = SUITES["splits"]
NAMES = ("tune", "validation", "test")


def test_splits_are_frozen():
    assert COMMITTED["seed"] == 20261030 and COMMITTED["frozen_on"]
    assert splits.is_frozen()
    with pytest.raises(RuntimeError):
        splits.write_frozen({}, [], 1, "2000-01-01")


def test_disjoint_and_complete():
    amazon = splits.amazon_cities()
    solomon = [n for s in NAMES for n in COMMITTED[s]["solomon"]]
    routes = [r for s in NAMES for r in COMMITTED[s]["amazon"]]
    assert len(solomon) == len(set(solomon)) == 56
    assert sorted(routes) == sorted(r for ids in amazon.values() for r in ids)
    assert len(routes) == 40


def test_stratified_thirds():
    expected = {"C1": 9, "C2": 8, "R1": 12, "R2": 11, "RC1": 8, "RC2": 8}
    for cls, n in expected.items():
        counts = [sum(1 for x in COMMITTED[s]["solomon"] if solomon_class(x) == cls) for s in NAMES]
        base, rem = divmod(n, 3)
        assert counts == [base, base + (rem >= 1), base + (rem >= 2)], cls
    for city, ids in splits.amazon_cities().items():
        counts = [sum(1 for r in COMMITTED[s]["amazon"] if r in ids) for s in NAMES]
        assert counts == [6, 7, 7], city


def test_regenerating_with_the_seed_gives_the_committed_splits():
    solomon = sorted(n for s in NAMES for n in COMMITTED[s]["solomon"])
    regenerated = splits.make_splits(solomon, splits.amazon_cities(), COMMITTED["seed"])
    for s in NAMES:
        assert regenerated[s]["solomon"] == COMMITTED[s]["solomon"]
        assert regenerated[s]["amazon"] == COMMITTED[s]["amazon"]


def test_quick_suite_is_a_stratified_tune_subset():
    quick = SUITES["suites"]["quick"]
    assert quick["split"] == "tune"
    tune = COMMITTED["tune"]
    assert set(quick["instances"]) <= set(tune["solomon"]) | set(tune["amazon"])
    assert quick["instances"] == splits.make_quick(tune, splits.amazon_cities(), COMMITTED["seed"])
    val = COMMITTED["validation"]
    assert not set(quick["instances"]) & (set(val["solomon"]) | set(val["amazon"]))
    classes = Counter(solomon_class(n) for n in quick["instances"] if not n.startswith("Route"))
    assert classes == Counter({c: 1 for c in ["C1", "C2", "R1", "R2", "RC1", "RC2"]})
    assert quick["seeds"] == [1, 2] and quick["time_limit_seconds"] == 5
    full = SUITES["suites"]["full"]
    assert full["seeds"] == [1, 2, 3, 4, 5] and full["time_limit_seconds"] == 30
    assert not set(full["aa_seeds"]) & set(full["seeds"])
