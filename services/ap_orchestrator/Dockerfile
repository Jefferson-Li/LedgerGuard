FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app
COPY services/ap_orchestrator/pyproject.toml /app/service/pyproject.toml
WORKDIR /app/service
RUN uv sync --no-dev

COPY services/ap_orchestrator /app/agents/ap_orchestrator
COPY services/redact.py /app/agents/redact.py
COPY services/gcp_auth.py /app/agents/gcp_auth.py

ENV PATH="/app/service/.venv/bin:${PATH}" \
    PYTHONPATH=/app/agents \
    PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8080
CMD ["sh", "-c", "adk web --host 0.0.0.0 --port ${PORT:-8080} /app/agents"]
