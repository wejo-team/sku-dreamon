# 고정 의존성을 비root 단일 프로세스 API 이미지에 담는다.
FROM ghcr.io/astral-sh/uv:0.11.30 AS uv
FROM python:3.13.14-slim-bookworm AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /opt/app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM python:3.13.14-slim-bookworm AS runtime
ARG RELEASE_SHA
RUN test "${#RELEASE_SHA}" -eq 40 && case "$RELEASE_SHA" in *[!0-9a-f]*) exit 1;; esac
LABEL org.opencontainers.image.revision=$RELEASE_SHA
ENV PATH="/opt/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
COPY --from=dependencies /opt/app/.venv ./.venv
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini backend/pyproject.toml backend/uv.lock ./
USER 10001:10001
EXPOSE 8000
STOPSIGNAL SIGTERM
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers", "--timeout-graceful-shutdown", "450"]
