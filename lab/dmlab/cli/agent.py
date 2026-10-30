"""dmlab-agent: run one experiment agent cycle.

  uv run --group ml dmlab-agent cycle --confirm-top 1
  uv run --group ml dmlab-agent cycle --offline --quick-only
  uv run --group ml dmlab-agent cycle --budgets /path/to/low_budgets.yaml

The model comes from LAB_LLM_MODEL (or LAB_LLM_OFFLINE_MODEL with --offline),
read from the environment or the repo's .env file. Only the variables listed
in ENV_KEYS are read from .env; values are never printed.
"""

import argparse
import os
from pathlib import Path

from dmlab.paths import BUDGETS_ENV, LAB_DIR

REPO_ENV = LAB_DIR.parent / ".env"
ENV_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "LAB_LLM_MODEL",
    "LAB_LLM_OFFLINE_MODEL",
    "OLLAMA_API_BASE",
    "LAB_QDRANT_URL",
)
DEFAULT_WORKERS = 5  # performance cores on the lab Mac; same as dmlab-harness


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


def cmd_cycle(args: argparse.Namespace) -> None:
    if args.budgets:
        os.environ[BUDGETS_ENV] = str(Path(args.budgets).resolve())
    load_env()
    # Imported after the environment is set up.
    from dmlab.agent.cycle import run_cycle
    from dmlab.agent.evaluate import confirmation_suite, screening_suite
    from dmlab.agent.llm import MAIN_MODEL_ENV, OFFLINE_MODEL_ENV, LiteLLMClient
    from dmlab.agent.memory import ExperimentMemory
    from dmlab.agent.report import to_markdown
    from dmlab.harness.runners import LocalRunner

    env = OFFLINE_MODEL_ENV if args.offline else MAIN_MODEL_ENV
    model = args.model or os.environ.get(env, "")
    if not model:
        raise SystemExit(f"set {env} (in the environment or .env) or pass --model")
    report = run_cycle(
        llm=LiteLLMClient(model),
        memory=ExperimentMemory.connect(),
        runner=LocalRunner(args.workers),
        quick_suite=screening_suite(),
        full_suite=confirmation_suite(),
        session=args.session,
        offline=args.offline,
        quick_only=args.quick_only,
        confirm_top=args.confirm_top,
        tracing=not args.no_tracing,
    )
    print()
    print(to_markdown(report))
    print(f"Cycle report: MLflow run {report['mlflow_cycle_run_id']} (cycle_report.md / .json)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="dmlab-agent", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cycle", help="run one agent cycle")
    c.add_argument("--offline", action="store_true", help="use LAB_LLM_OFFLINE_MODEL (Ollama)")
    c.add_argument("--model", help="override the model name")
    c.add_argument("--quick-only", action="store_true", help="screening only, no confirmation")
    c.add_argument("--confirm-top", type=int, default=2, choices=[1, 2])
    c.add_argument("--session", help="continue an LLM budget session (default: a new one)")
    c.add_argument("--budgets", help="budgets file with the structure of configs/budgets.yaml")
    c.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    c.add_argument("--no-tracing", action="store_true", help="disable MLflow tracing")
    c.set_defaults(func=cmd_cycle)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
