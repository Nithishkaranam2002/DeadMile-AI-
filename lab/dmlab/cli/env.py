"""Read the few settings the lab CLIs need from the repo's .env file.

Only the variables listed in ENV_KEYS are copied, and only when not already
set in the environment. Values are never printed.
"""

import os
from pathlib import Path

from dmlab.paths import LAB_DIR

REPO_ENV = LAB_DIR.parent / ".env"
ENV_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "LAB_LLM_MODEL",
    "LAB_LLM_OFFLINE_MODEL",
    "OLLAMA_API_BASE",
    "LAB_QDRANT_URL",
    # The dmlab database (kill switch, gates, approvals, audit log).
    "DMLAB_DB_URL",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "LAB_POSTGRES_PORT",
    "DMLAB_KILL_SWITCH",
)


def load_env(path: Path = REPO_ENV) -> list[str]:
    """Copy ENV_KEYS from .env into the environment when not already set."""
    if not path.exists():
        return []
    from dotenv import dotenv_values

    values = dotenv_values(path)
    loaded = []
    for key in ENV_KEYS:
        if not os.environ.get(key) and values.get(key):
            os.environ[key] = values[key]
            loaded.append(key)
    return loaded
