# MLflow tracking server for the lab. The version matches lab/pyproject.toml.
FROM python:3.12-slim

RUN pip install --no-cache-dir mlflow==3.17.2 psycopg2-binary==2.9.13

WORKDIR /mlflow
RUN mkdir -p /mlflow/artifacts
COPY docker/mlflow_entrypoint.py /usr/local/bin/mlflow_entrypoint.py

ENV PYTHONUNBUFFERED=1
EXPOSE 5000

CMD ["python", "/usr/local/bin/mlflow_entrypoint.py"]
