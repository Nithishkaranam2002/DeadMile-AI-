"""Start the lab MLflow tracking server.

Creates the `mlflow` database in the existing Postgres if it is missing, then
replaces this process with `mlflow server`. The backend store URI is handed to
MLflow through the MLFLOW_BACKEND_STORE_URI environment variable, so the
database password never appears in logs or in the process command line.
"""

import os
import sys
import time
from urllib.parse import quote

import psycopg2
from psycopg2 import sql


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        sys.exit(f"mlflow-entrypoint: required environment variable {name} is not set")
    return value


def ensure_database(host: str, port: str, user: str, password: str, db_name: str) -> None:
    for attempt in range(1, 31):
        try:
            conn = psycopg2.connect(
                host=host, port=port, user=user, password=password, dbname="postgres"
            )
            break
        except psycopg2.OperationalError:
            print(f"mlflow-entrypoint: waiting for Postgres at {host}:{port} ({attempt}/30)")
            time.sleep(2)
    else:
        sys.exit("mlflow-entrypoint: Postgres not reachable, giving up")

    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        if cur.fetchone():
            print(f"mlflow-entrypoint: database '{db_name}' already exists")
        else:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
            print(f"mlflow-entrypoint: created database '{db_name}'")
    conn.close()


def main() -> None:
    host = env("POSTGRES_HOST", "postgres")
    port = env("POSTGRES_PORT", "5432")
    user = env("POSTGRES_USER")
    password = env("POSTGRES_PASSWORD")
    db_name = env("MLFLOW_DB_NAME", "mlflow")

    ensure_database(host, port, user, password, db_name)

    credentials = f"{quote(user, safe='')}:{quote(password, safe='')}"
    os.environ["MLFLOW_BACKEND_STORE_URI"] = (
        f"postgresql+psycopg2://{credentials}@{host}:{port}/{db_name}"
    )
    os.environ.pop("POSTGRES_PASSWORD", None)

    args = [
        "mlflow",
        "server",
        "--host",
        "0.0.0.0",
        "--port",
        "5000",
        "--serve-artifacts",
        "--artifacts-destination",
        "/mlflow/artifacts",
        "--allowed-hosts",
        env("MLFLOW_ALLOWED_HOSTS"),
    ]
    print(f"mlflow-entrypoint: starting MLflow, backend database '{db_name}' on {host}:{port}")
    sys.stdout.flush()
    os.execvp(args[0], args)


if __name__ == "__main__":
    main()
