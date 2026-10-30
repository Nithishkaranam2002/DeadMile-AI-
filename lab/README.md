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

No results exist yet. Every number the lab reports will come from a run logged in MLflow.
