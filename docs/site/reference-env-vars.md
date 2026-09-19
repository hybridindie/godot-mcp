---
type: index
title: "Environment variables"
description: "Every configuration knob on both the server and the addon."
created: 2026-09-19
updated: 2026-09-19
---

# Environment variables

All knobs are optional; the defaults serve a local single-user setup.

## Server

| Variable | Default | Meaning |
|----------|---------|---------|
| `GODOT_MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `GODOT_MCP_HTTP_HOST` | `127.0.0.1` | HTTP bind host |
| `GODOT_MCP_HTTP_PORT` | `9090` | HTTP bind port (`/mcp` is FastMCP's mount path) |
| `GODOT_MCP_AUTH_TOKEN` | unset | Bearer token; **required** for non-loopback HTTP binds (fail-fast, #226) |
| `GODOT_MCP_BRIDGE_URL` | `ws://127.0.0.1:9080` | bridge listen (server) / connect (addon) URL |
| `GODOT_MCP_PROJECT_DIR` | unset | explicit project dir; else the connected editor's project is used |
| `GODOT_MCP_DEFAULT_TOOLSETS` | unset (= `inspection`) | seed the initial enabled toolsets: `all` or a comma-separated list (e.g. `scene_edit,runtime`); unknown names are logged and ignored |

## Addon (read in the editor's environment)

| Variable | Default | Meaning |
|----------|---------|---------|
| `GODOT_MCP_BRIDGE_URL` | `ws://127.0.0.1:9080` | where the addon dials the server (same var as the server) |
| `GODOT_BIN` | `godot` on PATH | the Godot binary (used by the server's headless runs; set as an Actions var on CI) |

## Security model

| Mode | Bind | Auth | Why |
|------|------|------|-----|
| `stdio` (default) | N/A (local subprocess) | none | only the spawning client can talk to it |
| `http` on loopback | `127.0.0.1` | none | only local processes reach it |
| `http` non-loopback | `0.0.0.0` / external IP | **`GODOT_MCP_AUTH_TOKEN` required** | the server refuses to start otherwise (#226) — without a token, anyone on the network could write scripts, run the game, or export builds through your editor |

```bash
# Generate + set a token
TOKEN=$(openssl rand -hex 32)
GODOT_MCP_TRANSPORT=http GODOT_MCP_HTTP_HOST=0.0.0.0 GODOT_MCP_AUTH_TOKEN=$TOKEN \
  uv run godot-editor-mcp
```

Clients pass the same token (HTTP `Authorization: Bearer …` header).

## Logging

Logs are one JSON object per line on **stderr** (stdout is the stdio protocol
channel). Every log line carries the command `id` where applicable; errors
include exception info. No secrets or full file contents are logged.