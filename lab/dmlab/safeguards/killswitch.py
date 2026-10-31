"""Kill switch: stops all agent activity.

On when either is set:
* the env var DMLAB_KILL_SWITCH (1, true, on, yes), or
* the flag in Postgres (table kill_switch), set with
  ``dmlab-safeguards kill on --reason ...``.

``check`` runs before every solve run (every runner, before each task is
started), before every LLM call, and before gate and shadow runs. It fails
closed: when the database cannot be read, the switch counts as on.

What stops: no new solve run or LLM call starts. A solve already running in a
host worker finishes (at most the suite's time limit); a sandbox container is
killed at once. The agent records the reason and goes straight to its report.
"""

import os

import sqlalchemy as sa
from pydantic import BaseModel

from dmlab.safeguards import audit, db

ENV = "DMLAB_KILL_SWITCH"
TRUE = {"1", "true", "on", "yes"}


class KillSwitchActive(RuntimeError):
    pass


class KillStatus(BaseModel):
    active: bool
    source: str  # env | postgres | database unreachable | off
    reason: str = ""
    actor: str | None = None
    changed_at: str | None = None


def status() -> KillStatus:
    env = os.environ.get(ENV, "").strip().lower()
    if env in TRUE:
        return KillStatus(active=True, source="env", reason=f"{ENV}={env}")
    try:
        with db.engine().connect() as c:
            row = c.execute(sa.select(db.kill_switch).where(db.kill_switch.c.id == 1)).first()
    except Exception as exc:  # fail closed
        return KillStatus(
            active=True,
            source="database unreachable",
            reason=f"cannot read the kill switch, so it counts as on ({type(exc).__name__})",
        )
    if row is None:
        return KillStatus(active=False, source="off")
    return KillStatus(
        active=bool(row.active),
        source="postgres" if row.active else "off",
        reason=row.reason,
        actor=row.actor,
        changed_at=row.changed_at.isoformat() if row.changed_at else None,
    )


def check(where: str) -> None:
    """Raise KillSwitchActive when the switch is on."""
    s = status()
    if s.active:
        by = f" by {s.actor}" if s.actor else ""
        raise KillSwitchActive(f"kill switch on ({s.source}{by}: {s.reason}); stopped {where}")


def set_switch(active: bool, actor: str, reason: str = "") -> KillStatus:
    """Turn the Postgres flag on or off; writes an audit row in the same transaction."""
    if not actor.strip():
        raise ValueError("actor is required")
    values = {"active": active, "reason": reason, "actor": actor, "changed_at": db.now()}
    with db.engine().begin() as c:
        found = c.execute(sa.select(db.kill_switch.c.id).where(db.kill_switch.c.id == 1)).first()
        if found:
            c.execute(sa.update(db.kill_switch).where(db.kill_switch.c.id == 1).values(**values))
        else:
            c.execute(sa.insert(db.kill_switch).values(id=1, **values))
        audit.write(actor, "kill_on" if active else "kill_off", comment=reason, conn=c)
    return status()
