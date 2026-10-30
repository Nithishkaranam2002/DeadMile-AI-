"""Log a dummy run to a temporary local MLflow store and read it back.

Uses a SQLite store under pytest's tmp_path, so no MLflow server is needed.
The values below are test fixtures, not results.
"""

from pathlib import Path

import mlflow
import pytest
from mlflow import MlflowClient


@pytest.fixture
def local_tracking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    monkeypatch.setenv("MLFLOW_DISABLE_AGENT_HINT", "1")
    mlflow.set_tracking_uri(uri)
    yield uri
    mlflow.set_tracking_uri(None)


def test_dummy_run_roundtrip(local_tracking: str, tmp_path: Path) -> None:
    client = MlflowClient(tracking_uri=local_tracking)
    artifact_root = (tmp_path / "artifacts").as_uri()
    experiment_id = client.create_experiment("lab-smoke-test", artifact_location=artifact_root)

    with mlflow.start_run(
        experiment_id=experiment_id, run_name="dummy", tags={"purpose": "test"}
    ) as run:
        mlflow.log_params({"seed": 7, "solver": "dummy"})
        mlflow.log_metric("dummy_metric", 1.5)
        mlflow.log_text("hello lab", "notes/hello.txt")
        run_id = run.info.run_id

    fetched = client.get_run(run_id)
    assert fetched.info.artifact_uri.startswith(artifact_root)

    assert fetched.info.status == "FINISHED"
    assert fetched.data.params == {"seed": "7", "solver": "dummy"}
    assert fetched.data.metrics["dummy_metric"] == 1.5
    assert fetched.data.tags["purpose"] == "test"
    assert [a.path for a in client.list_artifacts(run_id, "notes")] == ["notes/hello.txt"]
    assert mlflow.artifacts.load_text(f"{fetched.info.artifact_uri}/notes/hello.txt") == (
        "hello lab"
    )
