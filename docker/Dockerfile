# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Pin uv to a specific version for reproducible builds.
COPY --from=ghcr.io/astral-sh/uv:0.6.0 /uv /usr/local/bin/uv

WORKDIR /app

# Copy only package metadata first so `uv sync` can be cached independently
# of source-code changes.
COPY pyproject.toml uv.lock ./
COPY LICENSE ./
COPY README.md ./

# Sync dependencies (production only — no dev group).
RUN uv sync --no-dev

# Now copy the source — changes here won't invalidate the dependency layer.
COPY mcp_server/ ./mcp_server/

# HTTP transport is the intended mode inside the container.
ENV GODOT_MCP_TRANSPORT=http
ENV GODOT_MCP_HTTP_HOST=0.0.0.0
ENV GODOT_MCP_HTTP_PORT=9090
ENV GODOT_MCP_BRIDGE_URL=ws://host.docker.internal:9080

EXPOSE 9090

# Healthcheck: verify the HTTP server is listening on its port.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import socket; s=socket.socket(); s.connect(('localhost', 9090)); s.close()"

ENTRYPOINT ["uv", "run", "godot-mcp"]
