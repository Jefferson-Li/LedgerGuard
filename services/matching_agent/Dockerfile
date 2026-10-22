FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app
COPY services/matching_agent/pyproject.toml /app/services/matching_agent/pyproject.toml
WORKDIR /app/services/matching_agent
RUN uv sync --no-dev

COPY services/matching_agent /app/services/matching_agent
COPY services/invoice_mcp /app/services/invoice_mcp
COPY services/redact.py /app/services/redact.py
COPY services/gcp_auth.py /app/services/gcp_auth.py
COPY policy/ap-policy.md /app/policy/ap-policy.md
COPY data /app/data

ENV PATH="/app/services/matching_agent/.venv/bin:${PATH}" \
    PYTHONPATH=/app/services \
    LEDGERGUARD_DATA_DIR=/app/data \
    LEDGERGUARD_POLICY_PATH=/app/policy/ap-policy.md \
    PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8080'))"
CMD ["sh", "-c", "uvicorn matching_agent.agent:a2a_app --host 0.0.0.0 --port ${PORT:-8080}"]
