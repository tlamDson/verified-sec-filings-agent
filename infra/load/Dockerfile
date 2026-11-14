# One image for the load stack: API replicas, ingest workers and the simulated models.
# Build context is the repository root; Dockerfile.dockerignore keeps everything but the
# Python package out of it (no node_modules, no data).
FROM python:3.12.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /usr/local/bin/uv

# Mount points the runtime user writes to. A new named volume copies the ownership of the
# image directory it is mounted on, so /rawcache must exist here, owned by uid 1000;
# otherwise Docker creates it owned by root and the workers cannot fill the raw cache.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /rawcache /results \
    && chown 1000:1000 /rawcache /results
USER 1000
WORKDIR /home/app/repo

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/home/app/repo/.venv/bin:$PATH

COPY --chown=1000 pyproject.toml uv.lock README.md ./
COPY --chown=1000 packages/sec-agent/pyproject.toml packages/sec-agent/
RUN uv sync --locked --no-dev --no-install-workspace

COPY --chown=1000 packages/sec-agent packages/sec-agent
RUN uv sync --locked --no-dev
