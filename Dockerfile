# ---- Stage 1: builder — has uv, installs everything ----
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1

COPY pyproject.toml README.md ./
COPY src ./src

RUN uv venv /opt/venv && \
    VIRTUAL_ENV=/opt/venv uv pip install --no-cache .

# ---- Stage 2: runtime — minimal, ships only the result ----
FROM python:3.12-slim-bookworm

RUN groupadd --system app && useradd --system --gid app app

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PORT=8080

USER app
EXPOSE 8080

CMD ["sh", "-c", "uvicorn finsight.app:app --host 0.0.0.0 --port ${PORT}"]
