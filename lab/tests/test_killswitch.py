"""Kill switch: env var or Postgres flag (SQLite here), checked before every
solve run and every LLM call; fails closed. Values are fixtures, not results."""

import pytest
import sqlalchemy as sa
from pydantic import BaseModel

from dmlab.agent.llm import FakeLLM
from dmlab.harness.runners import LocalRunner, SolverConfig, SolveTask
from dmlab.routing.runner import InstanceRef
from dmlab.safeguards import audit, db, killswitch
from tests.conftest import TINY_SOLOMON

TASK = SolveTask(
    group="g",
    config=SolverConfig(solver="nn"),
    ref=InstanceRef("fixture", str(TINY_SOLOMON)),
    seed=1,
    time_limit_s=1,
)


class Echo(BaseModel):
    x: int


@pytest.fixture
def switch_off():
    killswitch.set_switch(False, "test", "reset")
    yield
    killswitch.set_switch(False, "test", "reset")


def test_off_by_default_lets_runs_start(switch_off):
    assert not killswitch.status().active
    outs = list(LocalRunner(1).run([TASK, TASK]))
    assert len(outs) == 2 and all(o.error is None for o in outs)


def test_postgres_flag_stops_a_solve_run_and_is_audited(switch_off):
    s = killswitch.set_switch(True, "alice", "demo stop")
    assert s.active and s.source == "postgres" and s.actor == "alice"
    with pytest.raises(killswitch.KillSwitchActive, match="demo stop"):
        list(LocalRunner(1).run([TASK]))
    actions = [r["action"] for r in audit.rows(5)]
    assert actions[0] == "kill_on"


def test_switch_on_mid_batch_stops_before_the_next_task(switch_off):
    seen = []
    with pytest.raises(killswitch.KillSwitchActive):
        for out in LocalRunner(1).run([TASK, TASK, TASK]):
            seen.append(out)
            killswitch.set_switch(True, "bob", "mid batch")
    assert len(seen) == 1  # one worker: no second task started after the switch


def test_env_var_stops_an_llm_call(switch_off, monkeypatch):
    llm = FakeLLM({"Echo": ['{"x": 1}']})
    monkeypatch.setenv(killswitch.ENV, "1")
    with pytest.raises(killswitch.KillSwitchActive, match="LLM call"):
        llm.complete("propose", [{"role": "user", "content": "hi"}], Echo, 10)
    assert llm.calls == []
    monkeypatch.delenv(killswitch.ENV)
    assert llm.complete("propose", [{"role": "user", "content": "hi"}], Echo, 10).index == 1


def test_unreadable_database_fails_closed(switch_off, monkeypatch):
    monkeypatch.setenv(db.DB_URL_ENV, "sqlite:////nonexistent/dir/x.sqlite")
    s = killswitch.status()
    assert s.active and s.source == "database unreachable"
    with pytest.raises(killswitch.KillSwitchActive):
        killswitch.check("test")


def test_off_writes_an_audit_row(switch_off):
    killswitch.set_switch(True, "carol", "on")
    killswitch.set_switch(False, "carol", "off again")
    with db.engine().connect() as c:
        last = c.execute(sa.select(db.audit_log).order_by(db.audit_log.c.id.desc())).first()
    assert last.action == "kill_off" and last.actor == "carol" and last.comment == "off again"


def test_actor_is_required():
    with pytest.raises(ValueError):
        killswitch.set_switch(True, " ", "x")
