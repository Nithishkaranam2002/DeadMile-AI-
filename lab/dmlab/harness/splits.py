"""Frozen data splits and suite settings, read from configs/suites.yaml.

This is the only module in dmlab that reads configs/suites.yaml. It serves the
tune and validation splits to anyone, and refuses the test split. The test
split is read only through ``dmlab.safeguards.test_split`` (the promotion gate
code path), which calls ``_read_split("test")``; ``_read_split`` checks its
caller at runtime and tests/test_test_split_guard.py checks statically that no
other module reaches it.

Splits were created once by ``make_splits`` (``dmlab-harness make-splits``)
with a fixed seed, stratified by Solomon class and Amazon city, and committed.
Inside each stratum the sorted names are shuffled with the seed and dealt into
thirds; leftovers go to validation first, then test, because the paired tests
need instances there more than tuning does.
"""

import inspect
import random
from pathlib import Path
from typing import Any, Literal

import yaml

from dmlab.data.solomon import solomon_class
from dmlab.paths import CONFIG_DIR, LAB_DIR, datasets_config, load_config
from dmlab.routing.runner import InstanceRef

SUITES_FILE = CONFIG_DIR / "suites.yaml"
PublicSplit = Literal["tune", "validation"]
PUBLIC_SPLITS: tuple[str, ...] = ("tune", "validation")
SPLIT_NAMES = ("tune", "validation", "test")
# The only module allowed to read the test split.
GATE_MODULE = "dmlab.safeguards.test_split"
# Quick suite: this many validation instances per stratum.
QUICK_PER_SOLOMON_CLASS = 1
QUICK_PER_AMAZON_CITY = 2


def _suites() -> dict[str, Any]:
    return load_config("suites")


def amazon_cities() -> dict[str, list[str]]:
    """Committed Amazon subset: city -> route ids."""
    return yaml.safe_load((CONFIG_DIR / "amazon_subset.yaml").read_text())["selected"]


def _deal(names: list[str], seed: int, stratum: str) -> dict[str, list[str]]:
    order = sorted(names)
    random.Random(f"{seed}:{stratum}").shuffle(order)
    base, rem = divmod(len(order), 3)
    sizes = {"tune": base, "validation": base + (rem >= 1), "test": base + (rem >= 2)}
    out, start = {}, 0
    for split in SPLIT_NAMES:
        out[split] = sorted(order[start : start + sizes[split]])
        start += sizes[split]
    return out


def make_splits(
    solomon_names: list[str], amazon: dict[str, list[str]], seed: int
) -> dict[str, dict[str, list[str]]]:
    """Stratified thirds per Solomon class and per Amazon city. Pure function."""
    strata: dict[str, list[str]] = {}
    for name in solomon_names:
        strata.setdefault(solomon_class(name), []).append(name.upper())
    splits: dict[str, dict[str, list[str]]] = {
        s: {"solomon": [], "amazon": []} for s in SPLIT_NAMES
    }
    for stratum in sorted(strata):
        for split, names in _deal(strata[stratum], seed, stratum).items():
            splits[split]["solomon"] += names
    for city in sorted(amazon):
        for split, names in _deal(amazon[city], seed, city).items():
            splits[split]["amazon"] += names
    return splits


def make_quick(tune: dict[str, list[str]], amazon: dict[str, list[str]], seed: int) -> list[str]:
    """Seeded, stratified subset of the tune split for the quick suite.

    The agent screens on tune (quick suite), confirms on validation (full
    suite) and the gate uses test, so no split both selects and confirms.
    """
    strata: dict[str, list[str]] = {}
    for name in tune["solomon"]:
        strata.setdefault(solomon_class(name), []).append(name)
    city_of = {rid: city for city, ids in amazon.items() for rid in ids}
    for rid in tune["amazon"]:
        strata.setdefault(city_of[rid], []).append(rid)
    picked: list[str] = []
    for stratum in sorted(strata):
        k = QUICK_PER_AMAZON_CITY if stratum in amazon else QUICK_PER_SOLOMON_CLASS
        names = sorted(strata[stratum])
        picked += sorted(random.Random(f"{seed}:quick:{stratum}").sample(names, k))
    return picked


def is_frozen() -> bool:
    return _suites()["splits"].get("seed") is not None


def write_frozen(
    splits: dict[str, dict[str, list[str]]], quick: list[str], seed: int, frozen_on: str
) -> None:
    """Fill the split and quick suite lists into suites.yaml, once."""
    if is_frozen():
        raise RuntimeError("splits are already frozen in configs/suites.yaml; never regenerate")
    text = SUITES_FILE.read_text()

    def block(names: list[str], indent: int) -> str:
        pad = " " * indent
        return "\n" + "\n".join(f"{pad}- {n}" for n in names) if names else " []"

    text = text.replace("  seed: null\n", f"  seed: {seed}\n", 1)
    text = text.replace("  frozen_on: null\n", f"  frozen_on: '{frozen_on}'\n", 1)
    for split in SPLIT_NAMES:
        for kind in ("solomon", "amazon"):
            marker = f"__{split}_{kind}__"
            text = text.replace(marker, block(splits[split][kind], 6).lstrip(" "), 1)
    text = text.replace("__quick_instances__", block(quick, 6).lstrip(" "), 1)
    SUITES_FILE.write_text(text)
    if not is_frozen():
        raise RuntimeError("writing suites.yaml failed")


def refs_for_names(names: list[str]) -> list[InstanceRef]:
    """Instance refs for Solomon names and Amazon route ids, in the given order."""
    cfg = datasets_config()
    solomon_dir = LAB_DIR / cfg["solomon"]["raw_dir"]
    amazon_dir = LAB_DIR / cfg["amazon"]["processed_dir"]
    refs = []
    for name in names:
        if name.startswith("RouteID_"):
            path = amazon_dir / f"{name}.json"
            kind = "amazon"
        else:
            path = solomon_dir / f"{name.lower()}.txt"
            kind = "solomon"
        if not Path(path).exists():
            raise FileNotFoundError(f"instance {name} not found at {path}")
        refs.append(InstanceRef(kind, str(path)))
    return refs


def split_names(split: PublicSplit) -> list[str]:
    """Instance names of the tune or validation split. Never the test split."""
    if split not in PUBLIC_SPLITS:
        raise PermissionError(
            f"split {split!r} is not available here: the test split is read only by the "
            "promotion gate (dmlab.safeguards.test_split)"
        )
    s = _suites()["splits"][split]
    return [*s["solomon"], *s["amazon"]]


def split_refs(split: PublicSplit) -> list[InstanceRef]:
    return refs_for_names(split_names(split))


def _read_split(split: str) -> list[str]:
    """Any split, including test. Only the gate module may call this."""
    caller = inspect.getmodule(inspect.stack()[1].frame)
    caller_name = caller.__name__ if caller else None
    if split == "test" and caller_name != GATE_MODULE:
        raise PermissionError(f"the test split may only be read by {GATE_MODULE}")
    s = _suites()["splits"][split]
    return [*s["solomon"], *s["amazon"]]


def suite_settings() -> dict[str, Any]:
    """Seeds, time limits and statistics settings (no instance lists)."""
    data = _suites()
    suites = data["suites"]
    return {
        "split_seed": data["splits"]["seed"],
        "quick": {k: v for k, v in suites["quick"].items() if k != "instances"},
        "quick_instances": list(suites["quick"]["instances"]),
        "full": dict(suites["full"]),
        "statistics": dict(data["statistics"]),
        "slices": dict(data["slices"]),
    }
