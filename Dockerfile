# Read-only web viewer for the Nevernote archive. Serves an index built on the
# host (`make refresh`); the container gets only data/viewer, read-only.
# Built by `make viewer-up` with rootless Podman; CI builds it with Docker.

FROM ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424 AS uv

FROM docker.io/library/python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
# Dependencies first, for layer caching. Runtime deps only; hash-checked lock.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-group backup --no-install-project --no-editable
COPY src ./src
RUN uv sync --locked --no-dev --no-group backup --no-editable

# Runtime: the same Python base (the venv points at its interpreter), no uv,
# no build tools, no source tree.
FROM docker.io/library/python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
RUN groupadd --system --gid 10001 viewer \
    && useradd --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin viewer
COPY --from=build /app/.venv /app/.venv
USER viewer
ENV PATH=/app/.venv/bin:$PATH \
    DATA_DIR=/data \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=4)"]
CMD ["enex-viewer", "serve", "--no-index"]
