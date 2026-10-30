"""Variant schemas the experiment agent proposes, safest first.

1. ParameterVariant: solver settings (PyVRP 0.14 search settings or OR Tools
   first solution strategy and local search metaheuristic).
2. FormulationVariant: how the solver sees the problem (see
   dmlab/routing/formulation.py). Always measured on the original instance.
3. CodeVariant: plugin source code. The schema exists so proposals can be
   validated and logged, but every code variant is rejected until Module 4
   adds the sandbox.

There is no time limit field anywhere: the suite fixes the time limit, and a
solver with more time is not a fair comparison. Unknown fields are refused
(extra="forbid"), and invalid proposals are rejected and logged, never repaired.
"""

from typing import Annotated, Any, Literal

from ortools.constraint_solver import routing_enums_pb2
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from dmlab.agent.plugins.interface import PLUGIN_NAMES
from dmlab.harness.runners import SolverConfig
from dmlab.routing.formulation import Formulation
from dmlab.routing.pyvrp_solver import OPERATOR_NAMES

# Read from the installed OR Tools (9.15), not typed by hand.
FIRST_SOLUTION_STRATEGIES = tuple(
    n
    for n in routing_enums_pb2.FirstSolutionStrategy.Value.keys()  # noqa: SIM118 (protobuf enum)
    # EVALUATOR_STRATEGY needs a custom callback we do not provide.
    if n not in ("UNSET", "AUTOMATIC", "EVALUATOR_STRATEGY")
)
METAHEURISTICS = tuple(
    n
    for n in routing_enums_pb2.LocalSearchMetaheuristic.Value.keys()  # noqa: SIM118 (protobuf enum)
    if n not in ("UNSET", "AUTOMATIC")
)

Strict = ConfigDict(extra="forbid")


class ILSSettings(BaseModel):
    model_config = Strict
    num_iters_no_improvement: int | None = Field(default=None, ge=1_000, le=1_000_000)
    history_length: int | None = Field(default=None, ge=1, le=5_000)
    exhaustive_on_best: bool | None = None


class PenaltySettings(BaseModel):
    model_config = Strict
    solutions_between_updates: int | None = Field(default=None, ge=10, le=10_000)
    penalty_increase: float | None = Field(default=None, ge=1.0, le=5.0)
    penalty_decrease: float | None = Field(default=None, ge=0.1, le=1.0)
    target_feasible: float | None = Field(default=None, ge=0.05, le=0.95)
    feas_tolerance: float | None = Field(default=None, ge=0.0, le=0.5)


class NeighbourhoodSettings(BaseModel):
    model_config = Strict
    weight_wait_time: float | None = Field(default=None, ge=0.0, le=5.0)
    num_neighbours: int | None = Field(default=None, ge=5, le=100)
    symmetric_proximity: bool | None = None


class PerturbationSettings(BaseModel):
    model_config = Strict
    min_perturbations: int | None = Field(default=None, ge=1, le=100)
    max_perturbations: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def _order(self) -> "PerturbationSettings":
        lo, hi = self.min_perturbations, self.max_perturbations
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("min_perturbations must be <= max_perturbations")
        return self


class PyVRPSettings(BaseModel):
    model_config = Strict
    ils: ILSSettings | None = None
    penalty: PenaltySettings | None = None
    neighbourhood: NeighbourhoodSettings | None = None
    perturbation: PerturbationSettings | None = None
    operators: list[Literal[OPERATOR_NAMES]] | None = Field(default=None, min_length=1)  # type: ignore[valid-type]

    def to_params(self) -> dict[str, Any]:
        """Sectioned settings for PyVRPSolver; unset values stay PyVRP defaults."""
        out: dict[str, Any] = {}
        for section in ("ils", "penalty", "neighbourhood", "perturbation"):
            value = getattr(self, section)
            if value is not None:
                given = value.model_dump(exclude_none=True)
                if given:
                    out[section] = given
        if self.operators is not None:
            if len(set(self.operators)) != len(self.operators):
                raise ValueError("operators must be distinct")
            out["operators"] = list(self.operators)
        return out


class ORToolsSettings(BaseModel):
    model_config = Strict
    first_solution_strategy: Literal[FIRST_SOLUTION_STRATEGIES]  # type: ignore[valid-type]
    local_search_metaheuristic: Literal[METAHEURISTICS]  # type: ignore[valid-type]


class VariantBase(BaseModel):
    model_config = Strict
    name: str = Field(min_length=3, max_length=80)
    hypothesis: str = Field(min_length=10, max_length=600)
    rationale: str = Field(min_length=10, max_length=1200)
    expected_effect: str = Field(min_length=3, max_length=300)


class ParameterVariant(VariantBase):
    kind: Literal["parameter"]
    solver: Literal["pyvrp", "ortools"]
    pyvrp: PyVRPSettings | None = None
    ortools: ORToolsSettings | None = None

    @model_validator(mode="after")
    def _match_solver(self) -> "ParameterVariant":
        if self.solver == "pyvrp" and (self.pyvrp is None or self.ortools is not None):
            raise ValueError("a pyvrp parameter variant needs pyvrp settings and no ortools")
        if self.solver == "ortools" and (self.ortools is None or self.pyvrp is not None):
            raise ValueError("an ortools parameter variant needs ortools settings and no pyvrp")
        if self.solver == "pyvrp" and not self.pyvrp.to_params():
            raise ValueError("a pyvrp parameter variant must change at least one setting")
        return self


class FormulationVariant(VariantBase):
    """Applied on top of the champion's solver config."""

    kind: Literal["formulation"]
    formulation: Formulation

    @model_validator(mode="after")
    def _not_identity(self) -> "FormulationVariant":
        if self.formulation.is_identity():
            raise ValueError("a formulation variant must change at least one setting")
        return self


class CodeVariant(VariantBase):
    kind: Literal["code"]
    plugin: Literal[PLUGIN_NAMES]  # type: ignore[valid-type]
    source: str = Field(min_length=1, max_length=20_000)


Variant = Annotated[
    ParameterVariant | FormulationVariant | CodeVariant, Field(discriminator="kind")
]
VARIANT_ADAPTER: TypeAdapter[Any] = TypeAdapter(Variant)


class ProposalBatch(BaseModel):
    """What the LLM returns when proposing. Each variant is validated on its
    own, so one invalid proposal does not hide the others."""

    model_config = Strict
    variants: list[Variant]


class CodeVariantsDisabled(Exception):
    pass


def to_solver_config(
    v: ParameterVariant | FormulationVariant, champion: SolverConfig
) -> SolverConfig:
    if isinstance(v, ParameterVariant):
        params = v.pyvrp.to_params() if v.solver == "pyvrp" else v.ortools.model_dump()
        return SolverConfig(solver=v.solver, params=params)
    if isinstance(v, FormulationVariant):
        form = v.formulation.model_dump(exclude_defaults=True)
        return SolverConfig(
            solver=champion.solver,
            params=champion.params,
            plugins=champion.plugins,
            formulation={**champion.formulation, **form},
        )
    raise CodeVariantsDisabled("code variants are disabled until Module 4 (sandbox)")


def mentions_time_limit(raw: Any) -> bool:
    """True when any key in a raw proposal tries to set a time limit."""
    if isinstance(raw, dict):
        return any(
            ("time_limit" in str(k).lower() or str(k).lower() in {"runtime", "max_runtime"})
            or mentions_time_limit(v)
            for k, v in raw.items()
        )
    if isinstance(raw, list):
        return any(mentions_time_limit(x) for x in raw)
    return False
