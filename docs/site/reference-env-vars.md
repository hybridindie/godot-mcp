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
| `GODOT_MCP_BRIDGE_TOKEN` | unset | opt-in shared secret for the bridge handshake (#538) — when set, the addon must send the matching token as its first message or the peer is refused at the handshake; never logged |
| `GODOT_MCP_PROJECT_DIR` | unset | explicit project dir; else the connected editor's project is used |
| `GODOT_MCP_DEFAULT_TOOLSETS` | unset (= `inspection`) | seed the initial enabled toolsets: `all` or a comma-separated list (e.g. `scene_edit,runtime`); unknown names are logged and ignored |

## Addon (read in the editor's environment)

| Variable | Default | Meaning |
|----------|---------|---------|
| `GODOT_MCP_BRIDGE_URL` | `ws://127.0.0.1:9080` | where the addon dials the server (same var as the server) |
| `GODOT_MCP_BRIDGE_TOKEN` | unset | the same opt-in secret as the server — the addon authenticates with it as its first message after connecting; never logged |
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

### Bridge handshake auth (#538)

The editor↔server WebSocket bridge is localhost-only; the bridge token adds a
shared secret for shared/self-hosted runners and remote-editor setups. It is
**opt-in on each side** — unset means no auth (zero-config local dev, unchanged
path). Both sides read `GODOT_MCP_BRIDGE_TOKEN`.

| Server token | Addon token | Behavior |
|--------------|-------------|----------|
| unset | unset | today's path — no auth exchange (byte-identical) |
| set | set, matching | peer authenticated, everything serves |
| set | set, **mismatched** | structured refusal at the handshake; the addon drops into its reconnect/backoff loop and the dock log shows the refusal reason each attempt until the tokens agree |
| set | **unset** | refused at the handshake (the addon never authenticates) — same visible reconnect loop |
| **unset** | set | the server consumes the auth envelope as a control message and serves anyway (forward-compatible: a newer addon against an older server) |

A refusal happens **at the handshake** — never as per-command errors, never as a
silent drop. Tokens are compared in constant time and are **never logged** on
either side.

```bash
# Shared/self-hosted runner: pin the same token on both sides
TOKEN=$(openssl rand -hex 32)
GODOT_MCP_BRIDGE_TOKEN=$TOKEN uv run godot-editor-mcp          # server
GODOT_MCP_BRIDGE_TOKEN=$TOKEN godot --editor --path ./game     # the editor's env
```

## Logging

Logs are one JSON object per line on **stderr** (stdout is the stdio protocol
channel). Every log line carries the command `id` where applicable; errors
include exception info. No secrets or full file contents are logged.