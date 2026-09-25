FROM ghcr.io/astral-sh/uv:0.12.19 AS uv

FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Dependencies first, for layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-group backup --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-group backup

RUN useradd --system --uid 10001 viewer && mkdir /data && chown viewer /data
USER viewer

ENV PATH=/app/.venv/bin:$PATH \
    ENEX_DIR=/enex \
    DATA_DIR=/data \
    PYTHONUNBUFFERED=1
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=4)"]

# Rebuilds the index when the ENEX files changed, then serves.
CMD ["enex-viewer", "serve"]
