---
title: Remote access & OpenWebUI
description: Drive Godot over HTTP from another machine — OpenWebUI, Docker, VPN-from-a-phone.
---

# Remote access & OpenWebUI

godot-mcp's HTTP transport is built for remote/web front-ends: run the server
next to your editor, expose it with a bearer token, and drive it from a phone
or laptop via [OpenWebUI](https://openwebui.com) — or any MCP Streamable HTTP
client.

## 1. Run the server over HTTP with a token

```bash
GODOT_MCP_TRANSPORT=http GODOT_MCP_HTTP_HOST=0.0.0.0 \
GODOT_MCP_AUTH_TOKEN=<token> uv run godot-editor-mcp
```

Non-loopback binds **require** a token (fail-fast, #226). The addon still
connects to the bridge on `ws://<host>:9080`.

## 2. Godot + addon

Open your project with the addon enabled; the MCP dock should show
*connected* (green). For a separate machine, point
`GODOT_MCP_BRIDGE_URL=ws://<server-host>:9080` at the server.

## 3. Register in OpenWebUI

OpenWebUI ≥ 0.11 speaks MCP Streamable HTTP.

1. **Settings → Tools → Integrations → External tool servers → +**
2. Switch the type from OpenAPI to **MCP Streamable HTTP**:
   - **URL**: `http://<server-host>:9090/mcp`
   - **Auth**: Bearer → paste the same `GODOT_MCP_AUTH_TOKEN`
   - **ID**: a short, simple name (e.g. `godot`) — see the caveat below
3. Test the connection (the round-trip arrows) and save.

## 4. Enable function calling per model

Settings → Models → edit the model → Advanced Params → **Function calling =
`native`**. OpenWebUI's `default` mode never emits tool calls — this is the
most common "tools don't work" cause. Verified with small local models from
the `qwen2.5-coder`, `gemma`, and `llama3.1` families.

## 5. Try it

In a chat, enable the `godot` tool (wrench icon) and ask:

> *"show the scene tree from the current connected project"*

## Caveats

- **Tool-name prefixing.** OpenWebUI prefixes every tool with the integration
  ID (`godot_inspection_get_scene_tree` → `<id>_godot_inspection_get_scene_tree`).
  Keep the ID short, or instruct the model to ignore the prefix — small local
  models otherwise try to call tools under their literal prefixed names.
- **Toolset gating.** Only `core` + `inspection` are exposed by default; for
  scene editing the agent must first call `godot_enable_toolset("scene_edit")`
  — or prompt it: *"enable the scene_edit toolset, then add a button below the
  Quit button"*.

## Security

The token is the whole transport gate: an unauthenticated network endpoint
could write files, run arbitrary GDScript, and export builds through your
editor. The server validates it via `StaticTokenVerifier`; generate any random
string (`openssl rand -hex 32`) and keep it out of the repo.