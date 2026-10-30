"""Benchmark suites: which instances, which seeds, which time limit.

* quick: the frozen tune subset, 2 seeds, short time limit. Used during
  agent iterations (screening). Confirmation uses the full validation suite.
* full: every instance of a split, 5 seeds. Used by the gates.

Suites are built from tune or validation only; ``splits`` refuses the test
split, and the gate builds its own test suite through ``Suite.from_refs``.
"""

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from dmlab.harness import splits
from dmlab.routing.runner import InstanceRef


class Suite(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str  # "quick" or "full"
    split: str
    refs: list[InstanceRef]
    seeds: list[int]
    time_limit_s: float

    @property
    def instance_names(self) -> list[str]:
        return [
            Path(r.path).stem.upper() if r.kind == "solomon" else Path(r.path).stem
            for r in self.refs
        ]

    def fingerprint(self) -> str:
        """Hash of everything that defines the suite (paths are machine specific)."""
        body = json.dumps(
            {
                "name": self.name,
                "split": self.split,
                "instances": self.instance_names,
                "seeds": self.seeds,
                "time_limit_s": self.time_limit_s,
            },
            sort_keys=True,
        )
        return hashlib.sha256(body.encode()).hexdigest()[:16]

    def with_seeds(self, seeds: list[int]) -> "Suite":
        return self.model_copy(update={"seeds": list(seeds)})

    @classmethod
    def from_refs(
        cls, name: str, split: str, refs: list[InstanceRef], seeds: list[int], time_limit_s: float
    ) -> "Suite":
        return cls(name=name, split=split, refs=refs, seeds=seeds, time_limit_s=time_limit_s)


def quick_suite() -> Suite:
    s = splits.suite_settings()
    q = s["quick"]
    if q["split"] != "tune":
        raise ValueError("the quick suite must be a tune subset")
    names = s["quick_instances"]
    if not set(names) <= set(splits.split_names("tune")):
        raise ValueError("quick suite instances must all be in the tune split")
    return Suite(
        name="quick",
        split="tune",
        refs=splits.refs_for_names(names),
        seeds=list(q["seeds"]),
        time_limit_s=float(q["time_limit_seconds"]),
    )


def full_suite(split: splits.PublicSplit = "validation") -> Suite:
    f = splits.suite_settings()["full"]
    return Suite(
        name="full",
        split=split,
        refs=splits.split_refs(split),
        seeds=list(f["seeds"]),
        time_limit_s=float(f["time_limit_seconds"]),
    )


def aa_seeds() -> list[int]:
    return list(splits.suite_settings()["full"]["aa_seeds"])


def get_suite(name: str, split: splits.PublicSplit = "validation") -> Suite:
    if name == "quick":
        return quick_suite()
    if name == "full":
        return full_suite(split)
    raise ValueError(f"unknown suite {name!r}; choose quick or full")
