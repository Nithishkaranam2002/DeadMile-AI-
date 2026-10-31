"""The kill switch stops an agent cycle cleanly: before an LLM call, or
between solve runs. Fake LLM, tiny fixture, temporary stores."""

from dmlab.agent.llm import FakeLLM
from dmlab.safeguards import killswitch
from tests.test_agent_cycle import GOOD_PARAM, HYP, budgets, cycle, lab, reflection  # noqa: F401


class SwitchAfterPropose(FakeLLM):
    """Turns the kill switch on right after the propose call returns."""

    def _complete(self, messages, schema, max_output_tokens):
        out = super()._complete(messages, schema, max_output_tokens)
        if schema.__name__ == "ProposalBatch":
            killswitch.set_switch(True, "test operator", "stop the agent mid cycle")
        return out


def test_switch_on_before_the_cycle_stops_at_the_first_llm_call(lab):  # noqa: F811
    _, memory, tmp_path, mp = lab
    budgets(tmp_path, mp)
    killswitch.set_switch(True, "test operator", "maintenance")
    try:
        llm = FakeLLM({"HypothesisSet": [HYP]})
        rep = cycle(memory, llm, quick_only=True)
    finally:
        killswitch.set_switch(False, "test operator", "done")
    assert "kill switch on" in rep["stop_reason"] and "maintenance" in rep["stop_reason"]
    assert llm.calls == [] and rep["ranked"] == [] and rep["nominee"] is None


def test_switch_on_mid_cycle_stops_before_any_solve_run(lab):  # noqa: F811
    _, memory, tmp_path, mp = lab
    budgets(tmp_path, mp)
    llm = SwitchAfterPropose(
        {
            "HypothesisSet": [HYP],
            "ProposalBatch": [{"variants": [GOOD_PARAM]}],
            "Reflection": [reflection(["v01"])],
        }
    )
    try:
        rep = cycle(memory, llm, confirm_top=1)
    finally:
        killswitch.set_switch(False, "test operator", "done")
    assert "kill switch on" in rep["stop_reason"]
    (row,) = rep["ranked"]
    assert row["status"] == "rejected" and row["reason"].startswith("not run: kill switch")
    assert rep["nominee"] is None
    assert [c.node for c in llm.calls] == ["hypothesize", "propose"]  # reflect skipped
