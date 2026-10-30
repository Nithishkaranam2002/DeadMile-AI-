"""MLflow tracking setup and run provenance.

Every MLflow call in the lab goes through ``configure_mlflow``, which sets the
tracking URI explicitly from MLFLOW_TRACKING_URI (default
http://localhost:5050, the lab MLflow server). File based URIs are refused so
nothing is ever written to a stray mlruns folder; tests opt in to a temporary
local store with DMLAB_ALLOW_LOCAL_TRACKING=1.
"""

import os
import subprocess
from pathlib import Path

import mlflow
from pydantic import BaseModel

from dmlab.paths import LAB_DIR

DEFAULT_TRACKING_URI = "http://localhost:5050"


class GitInfo(BaseModel):
    commit: str
    dirty: bool
    changed_files: list[str]


def tracking_uri() -> str:
    uri = os.environ.get("MLFLOW_TRACKING_URI") or DEFAULT_TRACKING_URI
    is_server = uri.startswith(("http://", "https://"))
    if not is_server and os.environ.get("DMLAB_ALLOW_LOCAL_TRACKING") != "1":
        raise RuntimeError(
            f"MLFLOW_TRACKING_URI={uri!r} is not an http(s) server. The lab only logs "
            "to the MLflow server (default http://localhost:5050)."
        )
    return uri


def configure_mlflow() -> str:
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    uri = tracking_uri()
    mlflow.set_tracking_uri(uri)
    return uri


def git_info(repo: Path = LAB_DIR) -> GitInfo:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True
        ).stdout

    commit = git("rev-parse", "HEAD").strip()
    status = [line for line in git("status", "--porcelain").splitlines() if line.strip()]
    return GitInfo(commit=commit, dirty=bool(status), changed_files=[s[3:] for s in status])
