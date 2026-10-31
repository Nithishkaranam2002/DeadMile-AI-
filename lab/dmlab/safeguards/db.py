"""The lab's own database: ``dmlab`` in the existing Postgres (Module 4).

Holds the safeguard state that must survive a process and be shared by the
CLIs and lab-api: kill switch, test split uses, gate runs, approvals, the
audit log, shadow runs and sandbox events. LangGraph's Postgres checkpointer
keeps its own tables in the same database (see agent_tail.py).

Written with SQLAlchemy 2.1 Core (no ORM). The URL comes from DMLAB_DB_URL;
without it, it is built from POSTGRES_USER / POSTGRES_PASSWORD and the
localhost port the lab publishes (LAB_POSTGRES_PORT, default 5433). Tests
point DMLAB_DB_URL at a temporary SQLite file; the same code runs on both.

No location is stored here, so no PostGIS columns are needed.
"""

import os
from datetime import UTC, datetime
from functools import cache
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine, make_url

DB_URL_ENV = "DMLAB_DB_URL"
DB_NAME = "dmlab"

metadata = sa.MetaData()


def now() -> datetime:
    return datetime.now(UTC)


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


kill_switch = sa.Table(
    "kill_switch",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),  # always 1: one switch
    sa.Column("active", sa.Boolean, nullable=False),
    sa.Column("reason", sa.Text, nullable=False, default=""),
    sa.Column("actor", sa.Text, nullable=False),
    _ts("changed_at"),
)

# Every load of a test set by a gate. The count is shown on gate report cards
# and in the API; a high count means the test set should be refreshed.
test_set_uses = sa.Table(
    "test_set_uses",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("model_name", sa.Text, nullable=False),
    sa.Column("test_set", sa.Text, nullable=False),  # e.g. "routing test split <fingerprint>"
    sa.Column("version", sa.Text, nullable=False),
    sa.Column("gate_run_id", sa.Integer, nullable=False),
    _ts("used_at"),
)

# One gate run per challenger config: unique (model_name, config_key, attempt).
# attempt 2 exists only after an audited retry of an attempt that ended in an
# infrastructure error before any verdict.
gate_runs = sa.Table(
    "gate_runs",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("model_name", sa.Text, nullable=False),
    sa.Column("version", sa.Text, nullable=False),
    sa.Column("config_key", sa.Text, nullable=False),
    sa.Column("attempt", sa.Integer, nullable=False, default=1),
    sa.Column("source", sa.Text, nullable=False),  # agent | manual
    sa.Column("status", sa.Text, nullable=False),  # running | passed | failed | error
    sa.Column("actor", sa.Text, nullable=False),
    _ts("started_at"),
    _ts("finished_at", nullable=True),
    sa.Column("test_set", sa.Text, nullable=True),
    sa.Column("test_set_use_number", sa.Integer, nullable=True),
    sa.Column("mlflow_run_id", sa.Text, nullable=True),
    sa.Column("report_card_uri", sa.Text, nullable=True),
    sa.Column("checks", sa.JSON, nullable=True),
    sa.Column("error", sa.Text, nullable=True),
    sa.UniqueConstraint("model_name", "config_key", "attempt", name="one_gate_run_per_config"),
)

approvals = sa.Table(
    "approvals",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("model_name", sa.Text, nullable=False),
    sa.Column("version", sa.Text, nullable=False),
    sa.Column("config_key", sa.Text, nullable=False),
    sa.Column("label", sa.Text, nullable=False),
    sa.Column("source", sa.Text, nullable=False),  # agent | manual
    sa.Column("submitted_by", sa.Text, nullable=False),
    sa.Column("note", sa.Text, nullable=False, default=""),
    # awaiting_gate | gate_failed | gate_error | pending | approved | rejected
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("gate_run_id", sa.Integer, nullable=True),
    sa.Column("agent_thread_id", sa.Text, nullable=True),  # paused agent cycle, if any
    sa.Column("champion_version_at_submit", sa.Text, nullable=True),
    _ts("created_at"),
    _ts("decided_at", nullable=True),
    sa.Column("decided_by", sa.Text, nullable=True),
    sa.Column("comment", sa.Text, nullable=True),
    sa.UniqueConstraint("model_name", "version", name="one_approval_per_version"),
)

# Append only. Nothing in dmlab updates or deletes audit rows.
audit_log = sa.Table(
    "audit_log",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    _ts("at"),
    sa.Column("actor", sa.Text, nullable=False),
    sa.Column("action", sa.Text, nullable=False),
    sa.Column("model_name", sa.Text, nullable=True),
    sa.Column("version", sa.Text, nullable=True),
    sa.Column("previous_champion", sa.Text, nullable=True),
    sa.Column("report_card_url", sa.Text, nullable=True),
    sa.Column("comment", sa.Text, nullable=False, default=""),
    sa.Column("details", sa.JSON, nullable=True),
)

shadow_runs = sa.Table(
    "shadow_runs",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("approval_id", sa.Integer, nullable=False),
    sa.Column("model_name", sa.Text, nullable=False),
    sa.Column("version", sa.Text, nullable=False),
    sa.Column("champion_version", sa.Text, nullable=False),
    sa.Column("replay_set", sa.Text, nullable=False),
    sa.Column("label", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),  # running | done | error
    _ts("started_at"),
    _ts("finished_at", nullable=True),
    sa.Column("mlflow_run_id", sa.Text, nullable=True),
    sa.Column("results", sa.JSON, nullable=True),
    sa.Column("error", sa.Text, nullable=True),
)

sandbox_events = sa.Table(
    "sandbox_events",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    _ts("at"),
    sa.Column("config_key", sa.Text, nullable=False),
    sa.Column("plugin", sa.Text, nullable=False),
    sa.Column("label", sa.Text, nullable=False),  # e.g. "injected test variant"
    sa.Column("instance", sa.Text, nullable=True),
    sa.Column("seed", sa.Integer, nullable=True),
    # ok | blocked (import allowlist) | timeout | oom | error | killed (kill switch)
    sa.Column("outcome", sa.Text, nullable=False),
    sa.Column("detail", sa.Text, nullable=False, default=""),
    sa.Column("wall_s", sa.Float, nullable=True),
)


def db_url() -> str:
    url = os.environ.get(DB_URL_ENV)
    if url:
        return url
    user = os.environ.get("POSTGRES_USER", "deadmile")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    port = os.environ.get("LAB_POSTGRES_PORT", "5433")
    return sa.URL.create(
        "postgresql+psycopg",
        username=user,
        password=password or None,
        host="localhost",
        port=int(port),
        database=DB_NAME,
    ).render_as_string(hide_password=False)


def libpq_url(url: str | None = None) -> str:
    """The same database as a plain libpq URL (for psycopg / LangGraph)."""
    u = make_url(url or db_url())
    if not u.drivername.startswith("postgresql"):
        raise ValueError("the LangGraph Postgres checkpointer needs a Postgres URL")
    return u.set(drivername="postgresql").render_as_string(hide_password=False)


def is_postgres(url: str | None = None) -> bool:
    return make_url(url or db_url()).drivername.startswith("postgresql")


@cache
def _engine(url: str) -> Engine:
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("postgresql"):
        kwargs["connect_args"] = {"connect_timeout": 5}
    return sa.create_engine(url, **kwargs)


def engine() -> Engine:
    return _engine(db_url())


def init_db() -> list[str]:
    """Create the dmlab database (Postgres) if missing, then every table.
    Returns what was done. Safe to run again; never drops anything."""
    url = make_url(db_url())
    done = []
    if url.drivername.startswith("postgresql"):
        admin = url.set(database=os.environ.get("POSTGRES_DB", "deadmile"))
        eng = sa.create_engine(admin, isolation_level="AUTOCOMMIT")
        with eng.connect() as conn:
            exists = conn.execute(
                sa.text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}
            ).scalar()
            if not exists:
                conn.execute(sa.text(f'CREATE DATABASE "{url.database}"'))
                done.append(f"created database {url.database}")
        eng.dispose()
    metadata.create_all(engine())
    done.append(f"tables ready: {', '.join(sorted(metadata.tables))}")
    return done
