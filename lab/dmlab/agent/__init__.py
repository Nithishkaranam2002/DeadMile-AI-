"""Experiment agent (Module 3).

Set before LiteLLM is ever imported (checked in litellm 1.106.6):
* LITELLM_MODE=PRODUCTION: otherwise LiteLLM calls load_dotenv() on import,
  finds the repo's .env (the product's settings: OTEL exporter endpoint,
  LITELLM_LOG, ...) and loads all of it into the agent's environment.
* LITELLM_LOCAL_MODEL_COST_MAP=True: prices come from the installed LiteLLM
  package (reproducible, works offline) instead of a map fetched at import.

Also MLFLOW_SUPPRESS_PRINTING_URL_TO_STDOUT: a cycle opens hundreds of runs,
and MLflow would print a link for each one.
"""

import os

os.environ.setdefault("LITELLM_MODE", "PRODUCTION")
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
os.environ.setdefault("MLFLOW_SUPPRESS_PRINTING_URL_TO_STDOUT", "true")
