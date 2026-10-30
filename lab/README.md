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
