FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /bin/uv

WORKDIR /piwikpro_analytics

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/piwikpro_analytics/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false \
    RUNTIME__DLTHUB_TELEMETRY=false \
    DUCKDB_PATH=/data/warehouse.duckdb

# Dependencies first, so this layer stays cached until the lockfile changes.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-install-project

COPY . .

# Installed at build time so running the container needs no network access.
RUN dbt deps --profiles-dir .

# The DuckDB file lives here so it survives the container: mount a host folder.
VOLUME /data

CMD ["sh", "-c", "python load/load.py && dbt build --profiles-dir ."]
