# syntax=docker/dockerfile:1.2

ARG ENV_MODE=prod
ARG PYTHON_VERSION=3.12.4

FROM python:${PYTHON_VERSION}-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

FROM base AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends git openssh-client sqlite3 libsqlite3-dev && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p -m 0600 ~/.ssh && \
    ssh-keyscan github.com >> ~/.ssh/known_hosts

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    python -m venv $VIRTUAL_ENV && \
    pip install --no-cache-dir -r requirements.txt

FROM base AS final

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder $VIRTUAL_ENV $VIRTUAL_ENV

COPY app /app/app

ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/nonexistent" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    appuser && \
    mkdir -p /app/logs && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app/logs

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
