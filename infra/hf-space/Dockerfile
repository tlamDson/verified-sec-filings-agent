# The API as a Docker Space on Hugging Face (free CPU). The deploy workflow stages this file
# at the root of the Space repository next to pyproject.toml, uv.lock and packages/sec-agent.
FROM python:3.12.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /usr/local/bin/uv

# Spaces run the container as uid 1000.
RUN useradd --create-home --uid 1000 app
USER 1000
WORKDIR /home/app/space

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/home/app/space/.venv/bin:$PATH \
    PORT=7860

# Dependencies first, so a code change does not reinstall them. No dev group and no `embed`
# extra: the Space serves BM25 search only (--lexical), without torch or a model.
COPY --chown=1000 pyproject.toml uv.lock README.md ./
COPY --chown=1000 packages/sec-agent/pyproject.toml packages/sec-agent/
RUN uv sync --locked --no-dev --no-install-workspace

COPY --chown=1000 . .
RUN uv sync --locked --no-dev

EXPOSE 7860
CMD ["sh", "start.sh"]
