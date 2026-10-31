"""dmlab-harness: frozen splits, champion registry, comparisons and self checks.

  uv run dmlab-harness make-splits                  # once, then commit configs/suites.yaml
  uv run dmlab-harness register-champion            # default PyVRP config -> @champion
  uv run dmlab-harness compare --candidate ortools --champion @champion --suite full
  uv run dmlab-harness selfcheck --suite full       # A/A and OR Tools vs champion

Only the tune and validation splits can be chosen here. The test split is
read only by the promotion gate.
"""

import argparse
import json
import sys
from datetime import date

from dmlab.cli.env import load_env
from dmlab.data.solomon import list_instances
from dmlab.harness import registry, splits
from dmlab.harness.compare import compare
from dmlab.harness.report_card import plain_words
from dmlab.harness.runners import LocalRunner, SolverConfig
from dmlab.harness.selfcheck import run_selfcheck
from dmlab.harness.suites import aa_seeds, get_suite
from dmlab.paths import LAB_DIR, datasets_config

SPLIT_SEED = 20261030
DEFAULT_WORKERS = 5  # performance cores on the lab Mac; see lab/README.md


def make_splits(_: argparse.Namespace) -> None:
    raw = LAB_DIR / datasets_config()["solomon"]["raw_dir"]
    names = [p.stem.upper() for p in list_instances(raw)]
    if len(names) != 56:
        raise SystemExit(f"expected 56 Solomon instances in {raw}, found {len(names)}")
    amazon = splits.amazon_cities()
    s = splits.make_splits(names, amazon, SPLIT_SEED)
    quick = splits.make_quick(s["tune"], amazon, SPLIT_SEED)
    splits.write_frozen(s, quick, SPLIT_SEED, date.today().isoformat())
    for name in splits.SPLIT_NAMES:
        print(f"{name:10s} solomon={len(s[name]['solomon'])} amazon={len(s[name]['amazon'])}")
    print(f"quick      {len(quick)} validation instances")


def _resolve(spec: str, params: str | None) -> tuple[SolverConfig, str | None]:
    if spec.startswith("@"):
        found = registry.get_alias(spec[1:])
        if found is None:
            raise SystemExit(f"{spec} is not set in the registry")
        version, cfg = found
        return cfg, f"{registry.MODEL_NAME} v{version} ({spec})"
    return SolverConfig(solver=spec, params=json.loads(params) if params else {}), None


def register_champion(_: argparse.Namespace) -> None:
    version = registry.bootstrap_champion(SolverConfig(solver="pyvrp"))
    print(f"registered {registry.MODEL_NAME} v{version} as @{registry.CHAMPION}")


def cmd_compare(args: argparse.Namespace) -> None:
    cand, cand_ref = _resolve(args.candidate, args.candidate_params)
    champ, champ_ref = _resolve(args.champion, None)
    suite = get_suite(args.suite, args.split)
    c, run_id = compare(
        cand,
        champ,
        suite,
        LocalRunner(args.workers),
        cand_ref,
        champ_ref,
        reuse_champion=not args.no_reuse,
        audit_reuse=args.audit_reuse,
    )
    for line in plain_words(c).values():
        print(line)
    print(f"champion runs reused from MLflow: {c.champion.reused_runs} of {c.champion.total_runs}")
    print(f"report card: MLflow run {run_id}, artifacts report_card.md / report_card.json")


def cmd_selfcheck(args: argparse.Namespace) -> None:
    champ, champ_ref = _resolve("@champion", None)
    suite = get_suite(args.suite, args.split)
    checks, _, run_id = run_selfcheck(
        champ,
        SolverConfig(solver="ortools"),
        suite,
        aa_seeds(),
        LocalRunner(args.workers),
        champ_ref,
    )
    for c in checks:
        print(f"{'PASS' if c.passed else 'FAIL'}  {c.name}  ({c.rule})  {c.observed}")
    print(
        f"MLflow selfcheck run {run_id}: nested runs 'A/A check: champion vs itself' and "
        "'Self check: ortools vs champion' hold the report cards; selfcheck.json the verdicts"
    )
    if not all(c.passed for c in checks):
        sys.exit(
            "SELF CHECK FAILED: the harness has a bug. Investigate; do not rerun with new seeds."
        )


def main() -> None:
    parser = argparse.ArgumentParser(prog="dmlab-harness")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("make-splits", help="freeze the splits once").set_defaults(func=make_splits)
    sub.add_parser("register-champion", help="register the first @champion").set_defaults(
        func=register_champion
    )

    def suite_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--suite", choices=["quick", "full"], default="quick")
        p.add_argument("--split", choices=list(splits.PUBLIC_SPLITS), default="validation")
        p.add_argument("--workers", type=int, default=DEFAULT_WORKERS)

    c = sub.add_parser("compare", help="candidate vs champion, logs a report card")
    c.add_argument("--candidate", required=True, help="solver name (pyvrp, ortools, nn) or @alias")
    c.add_argument("--candidate-params", help="JSON solver params for a named solver")
    c.add_argument("--champion", default="@champion")
    c.add_argument(
        "--no-reuse",
        action="store_true",
        help="run the champion fresh even when matching runs exist in MLflow",
    )
    c.add_argument(
        "--audit-reuse",
        type=int,
        default=0,
        metavar="K",
        help="solve K reused champion runs again and report how they compare",
    )
    suite_args(c)
    c.set_defaults(func=cmd_compare)
    s = sub.add_parser("selfcheck", help="A/A and OR Tools vs champion")
    suite_args(s)
    s.set_defaults(func=cmd_selfcheck)
    args = parser.parse_args()
    load_env()  # the kill switch reads the dmlab database
    args.func(args)


if __name__ == "__main__":
    main()
