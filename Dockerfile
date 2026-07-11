# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS python-builder
COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /uvx /usr/local/bin/
ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --compile-bytecode

FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        adb \
        bash \
        ca-certificates \
        coreutils \
        curl \
        git \
        gzip \
        tar \
        tini \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV HOME=/home/panel \
    MAA_AUTO_PANEL_CACHE_DIR=/app/cache \
    MAA_AUTO_PANEL_DATA_DIR=/app/data \
    PATH=/opt/venv/bin:/app/data/runtime/maa/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY --from=python-builder /opt/venv /opt/venv
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist
COPY docs/maa-cli/schemas /app/docs/maa-cli/schemas
COPY --chmod=0755 scripts/container-entrypoint /usr/local/bin/container-entrypoint

RUN groupadd --gid 10001 panel \
    && useradd --create-home --no-log-init --uid 10001 --gid 10001 panel \
    && mkdir -p /app/data /app/cache/downloads /home/panel/.android \
    && chown -R panel:panel /app /home/panel \
    && maa-auto-panel --help >/dev/null \
    && test -s /app/frontend/dist/index.html \
    && test -s /app/docs/maa-cli/schemas/task.schema.json

USER panel
EXPOSE 8000
ENTRYPOINT ["container-entrypoint"]
CMD ["maa-auto-panel", "webui", "--host", "0.0.0.0", "--port", "8000"]
