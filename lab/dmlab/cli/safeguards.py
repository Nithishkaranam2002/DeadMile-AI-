"""dmlab-safeguards: kill switch, database setup (Module 4).

  uv run dmlab-safeguards init-db
  uv run dmlab-safeguards kill on --reason "demo: stop the agent"
  uv run dmlab-safeguards kill off --reason "demo done"
  uv run dmlab-safeguards kill status

"Who" is the name given with --by (default: the OS user name). There is no
login yet, so it is self declared; the audit log records it as given.
"""

import argparse
import getpass
import json

from dmlab.cli.env import load_env


def _actor(args: argparse.Namespace) -> str:
    return args.by or getpass.getuser()


def cmd_init_db(_: argparse.Namespace) -> None:
    from dmlab.safeguards import db

    for line in db.init_db():
        print(line)


def cmd_kill(args: argparse.Namespace) -> None:
    from dmlab.safeguards import killswitch

    if args.state == "status":
        s = killswitch.status()
    else:
        s = killswitch.set_switch(args.state == "on", _actor(args), args.reason or "")
    print(json.dumps(s.model_dump(), indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="dmlab-safeguards", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db", help="create the dmlab database and tables").set_defaults(
        func=cmd_init_db
    )
    k = sub.add_parser("kill", help="kill switch: on, off or status")
    k.add_argument("state", choices=["on", "off", "status"])
    k.add_argument("--reason", default="")
    k.add_argument("--by", help="who (default: OS user name; self declared)")
    k.set_defaults(func=cmd_kill)
    args = parser.parse_args()
    load_env()
    args.func(args)


if __name__ == "__main__":
    main()
