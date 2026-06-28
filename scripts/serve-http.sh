#!/usr/bin/env bash
# Run godot-mcp as a long-lived HTTP service ("service mode").
#
# One server process owns the editor bridge (default ws://127.0.0.1:9080) and
# serves MCP over Streamable HTTP, so multiple clients — Claude Code AND the
# godot-agents project — drive the same live editor through it. (stdio spawns a
# per-client subprocess, which can't share the single editor bridge.)
#
# Clients point at  http://HOST:PORT/mcp/  (FastMCP's default mount path).
#
#   Claude Code   .mcp.json -> { "type": "http", "url": "http://127.0.0.1:9090/mcp/" }
#   godot-agents  GODOT_MCP_TRANSPORT=http  (defaults to the same host/port)
#
# Env overrides: GODOT_MCP_HTTP_HOST (127.0.0.1), GODOT_MCP_HTTP_PORT (9090),
#                GODOT_MCP_BRIDGE_URL (ws://127.0.0.1:9080).
set -euo pipefail

cd "$(dirname "$0")/.."

export GODOT_MCP_TRANSPORT=http
export GODOT_MCP_HTTP_HOST="${GODOT_MCP_HTTP_HOST:-127.0.0.1}"
export GODOT_MCP_HTTP_PORT="${GODOT_MCP_HTTP_PORT:-9090}"

echo "godot-mcp HTTP service -> http://${GODOT_MCP_HTTP_HOST}:${GODOT_MCP_HTTP_PORT}/mcp/" >&2
echo "editor bridge          -> ${GODOT_MCP_BRIDGE_URL:-ws://127.0.0.1:9080}" >&2

exec uv run godot-mcp "$@"
