"""dmlab-route: run route solvers and summarise results from MLflow.

  uv run dmlab-route solve --solver pyvrp,ortools,nn --instances solomon:all \
      --time-limit 30 --seed 1 --workers 4 --campaign m1-baselines
  uv run dmlab-route solve --solver nn --instances solomon:C101,R205
  uv run dmlab-route solve --solver pyvrp --instances amazon:boston
  uv run dmlab-route summary --campaign m1-baselines
"""

import argparse
import sys

import mlflow

from dmlab.routing.runner import EXPERIMENT, resolve_instances, run_batch
from dmlab.routing.solver import SOLVER_NAMES
from dmlab.routing.summary import build_rows, fetch_runs, sanity_problems, to_markdown
from dmlab.tracking import configure_mlflow, git_info


def solve(args: argparse.Namespace) -> None:
    solvers = [s.strip() for s in args.solver.split(",")]
    unknown = set(solvers) - set(SOLVER_NAMES)
    if unknown:
        raise SystemExit(f"unknown solver(s) {sorted(unknown)}; choose from {SOLVER_NAMES}")
    refs = resolve_instances(args.instances)
    results = run_batch(solvers, refs, args.time_limit, args.seed, args.workers, args.campaign)
    errors = [r for r in results if "error" in r]
    if errors:
        sys.exit(f"{len(errors)} run(s) crashed; see the log above and the batch run in MLflow")


def summary(args: argparse.Namespace) -> None:
    runs = fetch_runs(args.campaign)
    if not runs:
        raise SystemExit(f"no runs found for campaign {args.campaign!r}")
    rows = build_rows(runs)
    problems = sanity_problems(runs, rows)
    text = to_markdown(args.campaign, rows, problems)
    print(text)
    if args.log:
        configure_mlflow()
        mlflow.set_experiment(EXPERIMENT)
        git = git_info()
        tags = {
            "run_kind": "summary",
            "campaign": args.campaign,
            "git_commit": git.commit,
            "git_dirty": str(git.dirty).lower(),
        }
        with mlflow.start_run(run_name=f"summary {args.campaign}", tags=tags):
            mlflow.log_text(text, "summary.md")
            mlflow.log_dict({"rows": rows, "sanity_problems": problems}, "summary.json")
            mlflow.log_metric("sanity_problems", len(problems))
    if problems:
        sys.exit("SANITY CHECK FAILED: investigate before reporting these results")


def main() -> None:
    parser = argparse.ArgumentParser(prog="dmlab-route")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("solve", help="run solvers and log to MLflow")
    p.add_argument("--solver", required=True, help="pyvrp, ortools, nn, or a comma list")
    p.add_argument(
        "--instances",
        required=True,
        help="solomon:all | solomon:C101,R205 | amazon:boston | amazon:all | file:<path>; "
        "join groups with +",
    )
    p.add_argument("--time-limit", type=float, default=30.0, help="seconds per instance")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--campaign", default="adhoc", help="tag grouping runs for the summary")
    p.set_defaults(func=solve)
    s = sub.add_parser("summary", help="per solver and slice table from MLflow")
    s.add_argument("--campaign", required=True)
    s.add_argument("--log", action="store_true", help="also log the table to MLflow")
    s.set_defaults(func=summary)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
