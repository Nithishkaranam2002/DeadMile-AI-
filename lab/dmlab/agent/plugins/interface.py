"""Fixed plugin interface for code variants.

Code variants are LLM written Python that implements one of these protocols.
They always run inside the sandbox (separate container, no network, CPU and
memory limits, timeout, import allowlist checked by AST parsing). The sandbox
arrives in Module 4; until then every code variant is rejected and logged,
and ``SolveTask`` refuses any config that carries plugin code.

Planned plugins (Module 4):
* initial_solution: build a starting solution for the champion solver.
* stop_clustering: cluster first, route second (assign stops to clusters,
  then route each cluster).
"""

from typing import Protocol

PLUGIN_NAMES = ("initial_solution", "stop_clustering")
CODE_VARIANTS_ENABLED = False


class InitialSolutionBuilder(Protocol):
    def build(self, instance: dict) -> list[list[int]]:
        """Routes as lists of stop node indices (depot excluded)."""
        ...


class StopClusteringRule(Protocol):
    def assign(self, instance: dict, num_clusters: int) -> list[int]:
        """Cluster index for every stop, in stop order."""
        ...
