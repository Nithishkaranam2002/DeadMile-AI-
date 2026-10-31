"""Append only audit log: who did what, when, to which model version.

Actions: submit, gate_started, gate_passed, gate_failed, gate_error,
gate_retry_allowed, approve, reject, kill_on, kill_off.
"""

from typing import Any

import sqlalchemy as sa

from dmlab.safeguards import db


def write(
    actor: str,
    action: str,
    *,
    model_name: str | None = None,
    version: str | None = None,
    previous_champion: str | None = None,
    report_card_url: str | None = None,
    comment: str = "",
    details: dict[str, Any] | None = None,
    conn: sa.Connection | None = None,
) -> int:
    """Insert one row and return its id. Pass ``conn`` to write inside the
    caller's transaction, so the action and its audit row commit together."""
    row = {
        "at": db.now(),
        "actor": actor,
        "action": action,
        "model_name": model_name,
        "version": version,
        "previous_champion": previous_champion,
        "report_card_url": report_card_url,
        "comment": comment,
        "details": details,
    }
    if conn is not None:
        return int(conn.execute(sa.insert(db.audit_log).values(**row)).inserted_primary_key[0])
    with db.engine().begin() as c:
        return int(c.execute(sa.insert(db.audit_log).values(**row)).inserted_primary_key[0])


def rows(limit: int = 200, model_name: str | None = None) -> list[dict[str, Any]]:
    q = sa.select(db.audit_log).order_by(db.audit_log.c.id.desc()).limit(limit)
    if model_name:
        q = q.where(db.audit_log.c.model_name == model_name)
    with db.engine().connect() as c:
        return [dict(r._mapping) for r in c.execute(q)]
