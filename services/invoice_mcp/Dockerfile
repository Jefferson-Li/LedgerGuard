FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app
COPY services/invoice_mcp/pyproject.toml /app/services/invoice_mcp/pyproject.toml
WORKDIR /app/services/invoice_mcp
RUN uv sync --no-dev

COPY services/invoice_mcp /app/services/invoice_mcp
COPY data /app/data

ENV PATH="/app/services/invoice_mcp/.venv/bin:${PATH}" \
    PYTHONPATH=/app/services \
    LEDGERGUARD_DATA_DIR=/app/data \
    PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8080'))"
CMD ["python", "-m", "invoice_mcp.server"]
