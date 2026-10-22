FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app
COPY services/erp_mcp/pyproject.toml /app/services/erp_mcp/pyproject.toml
WORKDIR /app/services/erp_mcp
RUN uv sync --no-dev

COPY services/erp_mcp /app/services/erp_mcp
COPY services/redact.py /app/services/redact.py
COPY data /app/data

ENV PATH="/app/services/erp_mcp/.venv/bin:${PATH}" \
    PYTHONPATH=/app/services \
    LEDGERGUARD_DATA_DIR=/app/data \
    PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8080'))"
CMD ["python", "-m", "erp_mcp.server"]
