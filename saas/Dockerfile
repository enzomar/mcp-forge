FROM python:3.12-slim AS base
WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install Python deps (from saas/requirements.txt — context is repo root)
COPY saas/requirements.txt ./
RUN uv pip install --system --no-cache -r requirements.txt

# Install mcp-forge-generator from repo src/
COPY src/ ./mcp_forge_generator_src/
RUN uv pip install --system --no-cache ./mcp_forge_generator_src

# Copy SaaS application code
COPY saas/ .

# Non-root user + storage dirs
RUN useradd --create-home --uid 10001 appuser && \
    mkdir -p storage/outputs storage/tmp && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs')" || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
