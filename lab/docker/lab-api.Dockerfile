# Lab API (FastAPI). Build context is lab/.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.7.22 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON_PREFERENCE=only-system \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY dmlab/ ./dmlab/
COPY configs/ ./configs/
RUN uv sync --frozen --no-dev

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["/app/.venv/bin/uvicorn", "dmlab.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
