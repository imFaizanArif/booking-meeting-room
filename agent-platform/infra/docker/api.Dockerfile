# One image for api, worker, scheduler, migrations and the demo MCP servers.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/mock-mcp/pyproject.toml apps/mock-mcp/pyproject.toml
RUN mkdir -p apps/api/app apps/mock-mcp/mock_mcp && touch apps/api/app/__init__.py apps/mock-mcp/mock_mcp/__init__.py \
 && uv sync --frozen --no-dev --all-packages --no-install-workspace
COPY apps/api apps/api
COPY apps/mock-mcp apps/mock-mcp
RUN uv sync --frozen --no-dev --all-packages
RUN useradd --create-home --uid 10001 app && mkdir -p /var/lib/mock-mcp && chown app /var/lib/mock-mcp
USER app
ENV PATH="/app/.venv/bin:$PATH" MOCK_MCP_PYTHON=/app/.venv/bin/python MOCK_MCP_STATE_DIR=/var/lib/mock-mcp
WORKDIR /app/apps/api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
