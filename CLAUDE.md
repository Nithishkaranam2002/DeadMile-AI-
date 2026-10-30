# DeadMile AI: Pickup and Delivery Experiment Lab

## Why this work exists

DeadMile AI started as a load profitability tool for small truckload carriers. We are now adding a pickup and delivery (P&D) experiment lab, the kind of system an LTL carrier would use to improve its route planning safely. The lab must show four things working end to end:

1. An AI agent that proposes and tests changes to a route optimization model.
2. An evaluation harness that proves, with proper statistics, whether a change beats the current baseline.
3. Safeguards that stop bad or unproven changes before they reach "production", with a human approving every promotion.
4. Time series foundation models (Chronos 2) for pickup demand forecasting and ETA, benchmarked against classical baselines and fed back into route planning.

The demo story in one line: every improvement is measured against a baseline, every promotion passes gates and a human, and every result is shown in business terms (distance per stop, stops per driver hour, cost per stop, extra trips avoided).

## Hard rules

1. Never fabricate results. Every number shown in the UI, a report, or a README must come from a run logged in MLflow. No hardcoded metrics and no placeholder numbers that look real. If something has not been run yet, show "not run yet".
2. Label data honestly. Solomon instances are benchmark problems in abstract distance units, not miles. NYC taxi data is a proxy for pickup demand and travel time. Synthetic data is synthetic. Cost values are assumptions. The UI and every report must say this right next to those numbers.
3. No third party branding. Do not use any real carrier's name, logo, colors or data anywhere in code, UI or docs. The product is "DeadMile AI".
4. Do not guess library APIs. PyVRP, OR Tools, Chronos 2, MLflow, and LangGraph change often. Read the installed version's docs or source before writing calls. If unsure, check first, then write.
5. Reproducible runs. Every run sets and logs its seeds, config, data version, and git commit hash.
6. Phase 2 SaaS work is paused (NextAuth, GPT 4o mini load import, PWA, Load Compare). Do not modify or delete that code. Just do not extend it.
7. Ask me before: adding a new container, deleting files, changing an existing service, or downloading anything larger than 1 GB.
8. Plan before code. For each module, show me a plan and the list of files you will create or change, then wait for my OK.
9. Never game the gates. Do not lower thresholds, pick a weak champion, or cherry pick instances to make a challenger pass. If nothing passes, that is a real result and we show it as the system working.

## Existing stack (reuse it)

Seven microservices (api-gateway, agent-core, load-ingestion, load-processor, profitability-engine, market-intelligence, frontend). Postgres with PostGIS and TimescaleDB, Redis, Qdrant, MinIO, Kafka, Temporal. A LangGraph agent that calls LLMs through LiteLLM. XGBoost and K-Means models. Next.js 15 App Router frontend in services/frontend.

docker-compose.yml defines 19 services on deadmile-network: 8 start by default (postgres, redis, qdrant, api-gateway, agent-core, profitability-engine, market-intelligence, frontend) and 11 more under the full profile. docker-compose.prod.yml layers production overrides on top.

The lab plugs into this stack. It does not replace it. Follow the existing repo conventions from .cursorrules: Pydantic v2, type hints everywhere, async calls between services, secrets only through .env, and PostGIS GEOGRAPHY(POINT, 4326) for any location stored in Postgres.

## New pieces

| Need | Choice |
|---|---|
| Champion route solver | PyVRP 0.14 (iterated local search with late acceptance; earlier PyVRP versions used Hybrid Genetic Search. Supports time windows, pickups and deliveries, capacity) |
| Second solver baseline | Google OR Tools routing |
| Naive baseline | Nearest neighbor heuristic written by us |
| Instance reading | vrplib (supports Solomon format) or PyVRP's reader |
| Experiment tracking and registry | MLflow, Postgres backend, local artifact volume, aliases @champion and @challenger (stages are deprecated) |
| Statistics | scipy (Wilcoxon signed rank), numpy bootstrap |
| Forecasting baselines | statsforecast (seasonal naive, AutoETS), LightGBM, existing XGBoost |
| Foundation model | Chronos 2 (amazon/chronos-2, Apache 2.0), via chronos-forecasting or AutoGluon TimeSeries |
| Agent | LangGraph, with LLM calls through LiteLLM like the existing agent-core. Model name from env var LAB_LLM_MODEL. LiteLLM's per call cost tracking feeds the LLM budget |
| Experiment memory | Existing Qdrant |
| Lab API | FastAPI |
| Python tooling | uv, Python 3.12 (same as the existing services), pydantic v2, ruff, pytest |

## Folder layout

```
lab/
  pyproject.toml
  configs/
    suites.yaml        benchmark suites and frozen data splits
    gates.yaml         promotion gate thresholds
    budgets.yaml       compute, time and LLM cost limits
    business.yaml      cost assumptions for business views (always labeled as assumptions)
  dmlab/
    data/              loaders: solomon.py, amazon.py, taxi.py, synthetic.py
    routing/           problem model, solvers, independent feasibility checker, metrics
    harness/           suites, runners, statistics, compare, report card
    agent/             LangGraph experiment agent, variant schemas, plugins/interface.py
    safeguards/        gates, budgets, sandbox, kill switch, approvals, audit log, shadow mode
    forecasting/       forecasters, backtest, metrics
    sim/               service center day simulator (closes the loop)
    api/               FastAPI app used by the web pages
  tests/               small fixtures only, tests run without downloads
  data/                raw and processed data (gitignored except tiny fixtures)
```

New web pages go inside the existing Next.js app in services/frontend, as /lab routes in the App Router, following its current structure and styling. Check that Deck.gl is installed there before using it, and ask me before adding it.

## The problem we solve

One service center (the depot). A fleet of identical trucks, each with a capacity and a shift length limit. Each stop is either a delivery (freight that arrived overnight) or a pickup (freight a customer is sending out), with a time window and a service time.

Module 1 solves the static version, where all stops are known in the morning.
Module 5b adds the dynamic version, where some pickups are revealed during the day, inside the simulator.

Note: Solomon and Amazon instances have only one kind of demand, so load them as delivery only stops. Pickups come from the synthetic generator. The problem model must still support both kinds from the start.

## Data

| Dataset | Used for | Notes |
|---|---|---|
| Solomon VRPTW, 56 instances, 100 customers, classes C1, C2, R1, R2, RC1, RC2 | Solver benchmark | Store best known solutions in data/bks.csv with a source column. If a value cannot be verified, leave it empty. Most published Solomon best known solutions use a hierarchical objective (fewest vehicles first, then distance). Only report "gap to best known" when our objective matches, and state which objective. |
| Gehring and Homberger, 200 to 1000 customers | Scale tests | Optional |
| Amazon Last Mile Routing Research Challenge 2021 (AWS Open Data registry) | Realistic city days, use a subset of Boston and Chicago routes | Travel times are given in seconds. Distance is computed with haversine on stop coordinates, and we say so. |
| NYC TLC trip records | Pickup demand proxy (hourly pickups per zone), ETA proxy (hourly median trip duration for busy zone pairs) | Always labeled "proxy" |
| Synthetic service center pickups | Shows the known future covariate (pre booked pickups) | Generator seeded from Amazon stop locations, with weekly pattern, holidays and noise. Always labeled "synthetic". |

## Routing metrics

Computed from the final routes by our own code, never from solver internals.

1. Feasibility (must be 100% for any solver result we report): capacity, time windows, shift length, every stop visited exactly once.
2. Total distance and vehicles used.
3. Distance per stop.
4. Stops per driver hour: stops divided by total route duration in hours, including service time.
5. Time window violations.
6. Runtime.
7. Gap to best known solution, only when the objective matches.

Business view: cost per stop = (driver hours times cost per driver hour + distance times cost per distance unit) divided by stops. All cost values come from configs/business.yaml and are shown as assumptions.

## Evaluation harness rules

1. Splits are frozen in configs/suites.yaml, created once with a fixed seed and committed. They are stratified by Solomon class and by Amazon city. Three splits: tune, validation, test.
2. Two suite sizes. Quick suite: a validation subset, 2 seeds, short time limit, used during agent iterations. Full suite: all instances of a split, 5 seeds, used by gates.
3. Compare candidate vs champion with paired tests. Average seeds per instance first, then run a Wilcoxon signed rank test on per instance relative differences, plus a bootstrap 95% confidence interval of the median relative improvement.
4. Always report results per slice (each Solomon class and each Amazon city), not only the overall number.
5. The test split is used only by the promotion gate, once per nominated challenger. The agent never sees test metrics, only pass or fail. This prevents overfitting the benchmark and handles the problem of testing many candidates (select on validation, confirm once on test).
6. Every evaluation logs to MLflow and produces a one page report card (Markdown and JSON) as an artifact.

## Model registry

MLflow registry with aliases @champion and @challenger. A "model" can be a solver config, a plugin, or a forecaster. Each registry entry stores its config, plugin code if any, and its report card.

## Experiment agent

LangGraph graph:

load context, then hypothesize, then propose variants, then run, then evaluate, then reflect, then loop or stop, then nominate at most one challenger, then promotion gate, then human approval (graph interrupt).

Variant types, safest first:

1. Parameter variants: solver settings such as PyVRP 0.14 search settings (iterated local search: iterations without improvement before restart, late acceptance history length, exhaustive search on new best; penalty: update frequency, increase and decrease factors, target feasible share; neighbourhood: number of neighbours, wait time weight; perturbation: min and max perturbations; which local search operators are used), time limits, OR Tools first solution strategy and local search metaheuristic. PyVRP 0.14 has no population or crossover settings.
2. Formulation and policy variants: time window slack, max route duration, fleet size, capacity reserved for same day pickups, cluster first route second.
3. Code variants: LLM written Python that implements the fixed plugin interface in agent/plugins/interface.py, for example an initial solution builder or a stop clustering rule. Code variants always run inside the sandbox. They are disabled until Module 4.

Rules:

1. Proposals use structured output validated by pydantic. Invalid proposals are rejected and logged, never silently repaired.
2. Before proposing, the agent retrieves similar past experiments from Qdrant. After evaluating, it stores hypothesis, variant, result and lesson.
3. The agent iterates on the quick validation suite only. It has no code path that can load the test split.
4. Every cycle is one parent MLflow run with child runs per variant, including LLM token usage and cost.

## Safeguards

1. Feasibility gate: challenger feasible on 100% of gate instances.
2. Improvement gate (thresholds in gates.yaml, starting values): median relative distance improvement at least 0.5%, Wilcoxon p value below 0.05, bootstrap confidence interval lower bound above 0.
3. Regression gate: no slice worse than the champion by more than the tolerance in gates.yaml (start at 0.3%).
4. Runtime gate: challenger runtime at most 1.2 times the champion's.
5. Budgets from budgets.yaml: wall clock limit per run, LLM token and dollar cap per session, max variants per cycle, max CPU minutes per cycle. Hitting a budget stops cleanly and logs the reason.
6. Kill switch: a flag in Postgres plus an env var, checked before every run, stops all agent activity.
7. Sandbox: code variants run in a separate container with no network, CPU and memory limits, a timeout, and an import allowlist checked by AST parsing before execution.
8. Human approval: moving @champion requires approval on the Review page. Every approve or reject writes an audit log row (who, when, which version, report card link, comment).
9. Shadow mode: before approval, the challenger plans replayed days alongside the champion. Results are shown side by side and never used to act.

## Forecasting

1. Models: seasonal naive, AutoETS, LightGBM with lag and calendar features, existing XGBoost, Chronos 2 zero shot, Chronos 2 fine tuned. Optional: TimesFM (check its license first), TabPFN TS.
2. Chronos 2 uses known future covariates where available: day of week, holidays, pre booked pickups. It runs on CPU. GPU is optional.
3. Backtest: rolling origin, 8 to 12 forecast origins. Never shuffle time.
4. Metrics: WAPE, MASE scaled by seasonal naive, weighted quantile loss, 80% and 95% prediction interval coverage.
5. Significance: paired test across series and origins (Diebold Mariano or paired bootstrap).
6. Forecasters use the same registry and gate idea: champion vs challenger.

## Closed loop simulator

Simulates one service center day:

1. Morning plan with the champion solver.
2. Same day pickups revealed at random times during the day. Re-optimize every 30 minutes (configurable) and insert new pickups.
3. If a pickup cannot be inserted feasibly, count an extra dispatch (a second truck).
4. Policies compared: no forecast, reserve capacity using the P50 forecast, reserve capacity using the P90 forecast.
5. Outputs per policy: extra dispatches, total distance, distance per stop, on time pickup percentage, cost per stop, with confidence intervals across many seeded days.

## Web pages

1. /lab: business KPIs first, technical details behind a toggle.
2. /lab/experiments: experiment list and comparisons.
3. /lab/review/[id]: report card, slice deltas, shadow results, approve and reject buttons, audit log.
4. /lab/forecast: backtest results and closed loop results.
5. Deck.gl map: routes before and after for a selected instance or simulated day.
6. Optional what if box: I type a value per productivity point, it shows an illustrative annual dollar figure, clearly labeled "illustration, not a measured result".

All numbers come from the lab API, backed by MLflow and Postgres. Labels for proxy, synthetic and assumption values sit right next to the numbers.

## Engineering conventions

Python 3.12 with uv, type hints, pydantic v2 for configs and schemas, ruff, pytest. Configs in YAML. Tests use tiny fixtures and run in under 2 minutes without downloads.

Keep the lab separate from the existing product files:

1. Make targets are prefixed with lab, so the existing Makefile targets stay untouched: lab-up, lab-test, lab-lint, lab-demo.
2. Lab services go in a separate docker-compose.lab.yml, used together with the main docker-compose.yml on deadmile-network. The existing compose files stay unchanged.
3. lab-up starts only what the lab needs (postgres, qdrant, mlflow, lab-api), not the full profile. Add temporal or frontend only in the module that needs them.
4. Lab docs go in lab/ (lab/README.md, lab/DEMO.md). The existing README.md and DEMO.md at the repo root belong to the current product and are not changed.
5. Never run make clean or make db-reset. They delete Docker volumes and the database, which would also wipe all MLflow runs.

## Git and GitHub

1. All lab work happens on the lab branch. Never commit to main directly, never force push, never rewrite history.
2. Commit at small checkpoints, whenever one piece works and its tests pass. Use clear messages, for example "lab: add Solomon loader and tests".
3. Before every commit: run lab-test and lab-lint, check git status, and make sure no secrets or big files are staged. Never commit .env files, API keys, tokens, downloaded datasets, model weights or MLflow artifacts.
4. Push the lab branch to GitHub (origin) at the end of every module and at least once per working session. After pushing, tell me the branch and the last commit message.
5. Merge into main only when I ask, through a pull request on GitHub.
6. If a push fails (login, permissions, conflicts), stop and tell me the exact error. Do not change the remote URL or git credentials, and do not force push.

## Build order and status

| # | Module | Status |
|---|---|---|
| 0 | Lab setup (skeleton, MLflow, lab API) | done |
| 1 | Routing core and baselines | done |
| 2 | Evaluation harness | done |
| 3 | Experiment agent | not started |
| 4 | Safeguards and promotion gates | not started |
| 5a | Forecasting backtest | not started |
| 5b | Closed loop simulator | not started |
| 6 | Dashboard pages | not started |
| 7 | Optional: bandit guided experiments, ask the lab | not started |
| 8 | Demo prep | not started |

Update this table when a module is done.
