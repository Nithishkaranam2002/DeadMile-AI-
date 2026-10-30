"""The experiment agent graph (LangGraph 1.2, StateGraph with pydantic state).

    load_context -> hypothesize -> propose -> run_quick -> evaluate -> reflect
         ^____________________ loop (budget and cap allow) ______________|
                                                       | done
                                            confirm -> nominate -> [tail] -> finalize

* After every node, a stop reason (budget hit, failed LLM call) sends the
  graph straight to ``finalize``; no nomination happens after a stop.
* ``quick_only`` cycles go from reflect straight to finalize.
* ``tail`` holds the nodes that run after ``nominate`` and before
  ``finalize``. Module 4 passes the promotion gate and the human approval node
  (which calls ``langgraph.types.interrupt``) here, so the graph itself does not
  change. The graph is compiled with a checkpointer and run with a thread id,
  which the interrupt needs; Module 4 swaps the in-memory saver for Postgres.
"""

from collections.abc import Callable, Sequence
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from dmlab.agent import nodes
from dmlab.agent.state import CycleContext, CycleState

FINALIZE = "finalize"
Node = tuple[str, Callable[..., dict[str, Any]]]


def _or_finalize(next_node: str) -> Callable[[CycleState], str]:
    def route(state: CycleState) -> str:
        return FINALIZE if state.stop_reason else next_node

    return route


def _after_propose(state: CycleState) -> str:
    if state.stop_reason:
        return FINALIZE
    return "run_quick" if state.pending else "reflect"


def _after_reflect(state: CycleState) -> str:
    if state.stop_reason:
        return FINALIZE
    if state.keep_going:
        return "hypothesize"
    return FINALIZE if state.quick_only else "confirm"


def build_graph(tail: Sequence[Node] = (), checkpointer: Any = None) -> Any:
    g = StateGraph(CycleState, context_schema=CycleContext)
    main: list[Node] = [
        ("load_context", nodes.load_context),
        ("hypothesize", nodes.hypothesize),
        ("propose", nodes.propose),
        ("run_quick", nodes.run_quick),
        ("evaluate", nodes.evaluate),
        ("reflect", nodes.reflect),
        ("confirm", nodes.confirm),
        ("nominate", nodes.nominate),
        *tail,
        (FINALIZE, nodes.finalize),
    ]
    for name, fn in main:
        g.add_node(name, fn)
    g.add_edge(START, "load_context")
    g.add_conditional_edges("load_context", _or_finalize("hypothesize"))
    g.add_conditional_edges("hypothesize", _or_finalize("propose"))
    g.add_conditional_edges("propose", _after_propose)
    # run_quick -> evaluate -> reflect always, so the results of a round that a
    # budget stopped are still classified and stored in memory; reflect then
    # skips its LLM call and the route goes to finalize.
    g.add_edge("run_quick", "evaluate")
    g.add_edge("evaluate", "reflect")
    g.add_conditional_edges("reflect", _after_reflect)
    g.add_conditional_edges("confirm", _or_finalize("nominate"))
    after_nominate = [name for name, _ in tail] + [FINALIZE]
    g.add_edge("nominate", after_nominate[0])
    for a, b in zip(after_nominate, after_nominate[1:], strict=False):
        g.add_edge(a, b)
    g.add_edge(FINALIZE, END)
    return g.compile(checkpointer=checkpointer if checkpointer is not None else InMemorySaver())
