# DeadMile AI experiment lab

Pickup and delivery experiment lab. See `../CLAUDE.md` for the full design and rules.

## Commands (run from the repo root)

| Command | What it does |
|---|---|
| `make lab-up` | Start postgres, qdrant, MLflow (http://localhost:5050) and the lab API (http://localhost:8020/health) |
| `make lab-down` | Stop only MLflow and the lab API. Volumes are kept. |
| `make lab-test` | Run the lab tests (no server or downloads needed) |
| `make lab-lint` | Run ruff lint and format checks |

## Local environment

The lab uses a uv-managed Python 3.12 (pinned in `.python-version`, and
`python-preference = "only-managed"` in `pyproject.toml`).

```
cd lab
uv sync
uv run pytest
```

Every number the lab reports comes from a run logged in MLflow. This README
holds no results; read them from MLflow or with `dmlab-route summary`.

## Routing core (Module 1)

Solver runs happen on the Mac with `uv run`, not inside the lab-api container.
Every MLflow call sets the tracking URI explicitly from `MLFLOW_TRACKING_URI`
(default `http://localhost:5050`). File based URIs are refused, so nothing is
written to a stray `mlruns` folder. Each run logs its seed, config, data
version (sha256), git commit and `git_dirty` (with the changed file names).

```
cd lab
uv run dmlab-data fetch-solomon     # 56 Solomon instances (84 KB archive, SINTEF)
uv run dmlab-data build-bks         # data/bks.csv, each DIMACS value replayed by our checker
uv run dmlab-data fetch-amazon      # streams ~1,047 MB, keeps ~50 MB (Boston + Chicago subset)

uv run dmlab-route solve --solver pyvrp,ortools,nn --instances solomon:all+amazon:all \
    --time-limit 30 --seed 1 --workers 4 --campaign m1-baselines
uv run dmlab-route summary --campaign m1-baselines --log
```

Instance specs: `solomon:all`, `solomon:C101,R205`, `amazon:boston`,
`amazon:chicago`, `amazon:all`, `file:<Solomon format file>`; join with `+`.

### Solvers

| Name | What | Notes |
|---|---|---|
| `pyvrp` | PyVRP 0.14.1 (champion) | Iterated local search in this version. Seeded. |
| `ortools` | OR Tools 9.15 routing | PARALLEL_CHEAPEST_INSERTION + GUIDED_LOCAL_SEARCH. No seed parameter exists, so the seed is logged as unused. With PATH_CHEAPEST_ARC it found no first solution on Solomon R101/R105 in 30 s. |
| `nn` | Nearest neighbor, ours | Naive baseline, deterministic. May leave stops unvisited; then it is reported infeasible. |

Solvers return routes only. Feasibility and every metric are recomputed from
the routes by `dmlab/routing/feasibility.py` and `metrics.py`.

### Data and labels

* **Solomon** (benchmark, abstract units, not miles). Distances follow the
  DIMACS convention: integer distance = floor(10 x euclidean); travel time =
  distance; windows and service times x 10. Gap to best known is computed only
  against the distance only DIMACS values in `data/bks.csv`, which come from
  CVRPLIB (via the PyVRP Instances repository, pinned commit) and were each
  replayed by our checker. SINTEF values (fewest vehicles first, exact
  distances) are listed as reference only and never used for a gap.
* **Amazon Last Mile 2021, evaluation set** (CC BY-NC 4.0, non-commercial).
  One route = one instance; depot = the Station stop; demand = package volume
  (cm3); service = sum of planned service seconds; windows = intersection of
  package windows; durations = Amazon travel times (seconds). Distance =
  haversine straight-line km on stop coordinates, not road distance.
  Assumptions: 2 vans per route with the route's capacity, 10 h shift.
  Subset and selection rule: `configs/amazon_subset.yaml`.

## Evaluation harness (Module 2)

```
cd lab
uv run dmlab-harness make-splits          # done once (seed 20261030); refuses to run again
uv run dmlab-harness register-champion    # routing-solver v1 = default PyVRP config, @champion
uv run dmlab-harness compare --candidate ortools --suite quick
caffeinate -i uv run dmlab-harness compare --candidate ortools --suite full    # ~25 min
caffeinate -i uv run dmlab-harness selfcheck --suite full                      # ~40 min
```

* **Splits** (`configs/suites.yaml`, frozen and committed): thirds per Solomon
  class and per Amazon city, leftovers to validation then test. Solomon
  16 / 20 / 20, Amazon 12 / 14 / 14 (tune / validation / test).
* **Suites**: quick = 10 validation instances (1 per Solomon class, 2 per
  city), seeds 1-2, 5 s. Full = every instance of a split, seeds 1-5, 30 s.
  Seeds 6-10 are used only by the A/A self check.
* **Seeds**: seeded solvers (PyVRP) run every seed and are averaged per
  instance. Solvers without a seed (OR Tools, nearest neighbor) run once per
  instance.
* **Statistics** (`dmlab/harness/stats.py`): r = (champion - candidate) /
  champion per instance, so r > 0 means the candidate is better. Wilcoxon
  signed rank on r (exact ties dropped and counted), and a seeded bootstrap 95%
  CI of the median r. Instances where either solver was infeasible on any run
  are listed as not compared.
* **Report card**: `report_card.md` and `report_card.json` on the compare run
  in MLflow experiment `harness`. The card covers wins, losses and ties in
  plain words, the statistics, a table per slice and the labels. The compare
  run is the parent of two evaluation runs, and each evaluation run is the
  parent of one solve run per instance and seed.
* **Registry**: model `routing-solver`, aliases `@champion` and
  `@challenger`. `register-champion` only works while no champion exists.
  Moving the champion is left to the promotion gate with human approval
  (Module 4).
* **Test split**: only `dmlab/safeguards/test_split.py` (the gate code path)
  can read it. `tests/test_test_split_guard.py` proves this statically and at
  runtime. The CLI only accepts `--split tune|validation`.
* **Self checks**: A/A (champion seeds 1-5 vs 6-10) must not show a
  significant improvement (one sided p >= 0.05). OR Tools vs champion must
  show the champion better (median r < 0, CI upper bound < 0, one sided
  p < 0.05). A failed check means a harness bug. It is never rerun with other
  seeds.
* **Workers**: the default is 5, the number of performance cores on the lab
  Mac. Under a fixed time limit, a run on an efficiency core gets fewer
  iterations, which adds noise to the comparison.
* `LocalRunner` uses a process pool. A `TemporalRunner` can be added later
  with the same `SolveTask` / `TaskOutcome` contract (`dmlab/harness/runners.py`).
