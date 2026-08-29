# Stage 1: Build virtualenv using standard Python image with uv binary copied
FROM python:3.12-slim-bookworm AS builder

# Copy the uv binary from the official minimal image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uv

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
# Use copy link mode instead of hardlinks
ENV UV_LINK_MODE=copy

# Install dependencies using the copied uv binary
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    /uv sync --frozen --no-install-project --no-dev

# Stage 2: Final lightweight execution image
FROM python:3.12-slim-bookworm

# Create a non-root system user and group for container security
RUN groupadd -g 999 appgroup && \
    useradd -r -u 999 -g appgroup appuser

WORKDIR /app

# Copy the virtualenv from builder stage
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application source files, assigning ownership to the non-root user
COPY --chown=appuser:appgroup db/ /app/db/
COPY --chown=appuser:appgroup data/ /app/data/
COPY --chown=appuser:appgroup core/ /app/core/
COPY --chown=appuser:appgroup cli.py mcp_server.py main.py README.md /app/

# Create directories for SQLite DB and reports, ensuring appuser has write permissions
RUN mkdir -p /app/db/data /app/reports && \
    chown -R appuser:appgroup /app/db /app/reports

# Set DB path environment variable to point to persistent directory
ENV DB_PATH=/app/db/data/portfolio.db

# Expose port (8000 is used by FastMCP SSE transport by default)
EXPOSE 8000

# Switch to the non-root user
USER appuser

# Default command to run the MCP Server
CMD ["python", "mcp_server.py"]
