"""The promotion gate's only door to the test split.

Nothing else in dmlab may import this module (tests/test_test_split_guard.py
checks that statically). The Module 4 promotion gate imports it to evaluate a
nominated challenger once on the test split. The agent only ever sees the
gate's pass or fail, never test metrics.
"""

from dmlab.harness import splits
from dmlab.routing.runner import InstanceRef


def gate_test_names() -> list[str]:
    return splits._read_split("test")


def gate_test_refs() -> list[InstanceRef]:
    return splits.refs_for_names(gate_test_names())
