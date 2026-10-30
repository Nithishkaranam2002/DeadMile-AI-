"""Build data/bks.csv: best known solutions for the Solomon instances.

Two objectives, never mixed:

* distance_only / dimacs_trunc1: total distance with floor(10 * euclidean)
  arcs, no vehicle minimisation. Solutions (full routes) come from CVRPLIB via
  the PyVRP Instances repository at a pinned commit. Each one is replayed by
  our feasibility checker on our own load of the original Solomon file; the
  value is written only if the routes are feasible and our recomputed distance
  equals the published cost. Otherwise the distance is left empty.
  This is the only objective used for "gap to best known".
* hierarchical / exact_euclidean: fewest vehicles, then distance in double
  precision, as published on the SINTEF page. Reference only, no detailed
  routes are replayed, and it is never used for a gap.
"""

import csv
import html
import re
from datetime import date
from pathlib import Path

from dmlab.data.download import fetch_bytes
from dmlab.data.solomon import load_solomon, solomon_class
from dmlab.routing.feasibility import check

FIELDS = [
    "instance",
    "class",
    "objective",
    "distance_convention",
    "vehicles",
    "distance",
    "source",
    "verification",
    "verified_on",
]


def parse_sol(text: str) -> tuple[list[list[int]], float]:
    routes: list[list[int]] = []
    cost = None
    for line in text.splitlines():
        line = line.strip()
        if m := re.match(r"Route #\d+:\s*(.*)$", line):
            routes.append([int(t) for t in m.group(1).split()])
        elif m := re.match(r"Cost\s+([0-9.]+)$", line):
            cost = float(m.group(1))
    if cost is None or not routes:
        raise ValueError("solution file has no routes or no cost")
    return routes, cost


def parse_sintef(page: str) -> dict[str, tuple[int, str, str, str]]:
    """Return {instance: (vehicles, distance as printed, reference, page note)}.

    A few rows are labeled with a suffix (e.g. "r205b") and carry a comment
    about a corrected value; that comment is kept as the page note.
    """
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", "|", text))
    cells = [c.strip() for c in re.split(r"\s*\|\s*", text) if c.strip()]
    out: dict[str, tuple[int, str, str, str]] = {}
    for i in range(len(cells) - 4):
        m = re.fullmatch(r"((?:rc|r|c)[12]\d\d)([a-z]?)", cells[i])
        if not m or m.group(1).upper() in out:
            continue
        veh, dist, ref = cells[i + 1], cells[i + 2], cells[i + 3]
        if re.fullmatch(r"\d+", veh) and re.fullmatch(r"[0-9.]+\*?", dist):
            note = f"page label '{cells[i]}', page comment: {cells[i + 4]}" if m.group(2) else ""
            out[m.group(1).upper()] = (int(veh), dist, ref, note)
    return out


def build(solomon_dir: Path, cache_dir: Path, cfg: dict, out_csv: Path) -> list[dict]:
    today = date.today().isoformat()
    commit = cfg["dimacs_solutions_commit"]
    rows: list[dict] = []

    sintef_file = cache_dir / "sintef_100.htm"
    if not sintef_file.exists():
        sintef_file.write_bytes(fetch_bytes(cfg["sintef_url"], max_bytes=2_000_000))
    sintef = parse_sintef(sintef_file.read_text(encoding="utf-8", errors="replace"))

    sol_dir = cache_dir / "dimacs"
    sol_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(solomon_dir.glob("*.txt")):
        inst = load_solomon(path)
        name = inst.name
        sol_file = sol_dir / f"{name}.sol"
        url = cfg["dimacs_solutions_url"].format(commit=commit, name=name)
        if not sol_file.exists():
            sol_file.write_bytes(fetch_bytes(url, max_bytes=200_000))
        routes, cost = parse_sol(sol_file.read_text())
        report = check(inst, routes)
        ours = sum(r.distance for r in report.routes)
        published = round(cost * 10)
        ok = report.feasible and ours == published
        verification = (
            "routes replayed by dmlab checker: feasible, distance matches"
            if ok
            else f"NOT VERIFIED: feasible={report.feasible}, ours={ours / 10}, published={cost}"
        )
        rows.append(
            {
                "instance": name,
                "class": solomon_class(name),
                "objective": "distance_only",
                "distance_convention": "dimacs_trunc1",
                "vehicles": len(routes) if ok else "",
                "distance": f"{cost:.1f}" if ok else "",
                "source": f"CVRPLIB via github.com/PyVRP/Instances@{commit[:7]} VRPTW/Solomon/"
                f"{name}.sol",
                "verification": verification,
                "verified_on": today if ok else "",
            }
        )
        if name in sintef:
            veh, dist, ref, page_note = sintef[name]
            note = "as published, routes not replayed; reference only, never used for a gap"
            if dist.endswith("*"):
                note += "; marked * on the page (see the page's note about distance)"
            if page_note:
                note += f"; {page_note}"
            rows.append(
                {
                    "instance": name,
                    "class": solomon_class(name),
                    "objective": "hierarchical_vehicles_then_distance",
                    "distance_convention": "exact_euclidean",
                    "vehicles": veh,
                    "distance": dist.rstrip("*"),
                    "source": f"SINTEF {cfg['sintef_url']} (reference {ref})",
                    "verification": note,
                    "verified_on": today,
                }
            )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return rows


def load_dimacs_bks(csv_path: Path) -> dict[str, int]:
    """Verified distance only values, in internal units (x10)."""
    out: dict[str, int] = {}
    if not csv_path.exists():
        return out
    with csv_path.open() as f:
        for row in csv.DictReader(f):
            if (
                row["objective"] == "distance_only"
                and row["distance_convention"] == "dimacs_trunc1"
                and row["distance"]
                and row["verified_on"]
            ):
                out[row["instance"]] = round(float(row["distance"]) * 10)
    return out
