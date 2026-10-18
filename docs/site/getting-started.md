---
type: index
title: "Get started"
description: "Install Godot Editor MCP, connect your editor and AI assistant, and drive your first session."
created: 2026-09-19
updated: 2026-10-18
---

# Get started

Godot Editor MCP drives a **live Godot editor** through the addon. Pick the track that
matches what you want to do.

## For creators — let your AI assistant do it

You make games and use an AI assistant (Claude, Codex, ChatGPT…), and you would rather
not touch a terminal. Hand it the setup:

→ **[For creators](for-creators.md)** — the friendly on-ramp, including a one-paste
setup prompt. Your assistant installs the server, the addon, and the skills; you do one
click and start building.

## For developers — set it up yourself

You're comfortable with installs and MCP. Five steps:

1. **[Install the MCP server](getting-started-install.md)** — PyPI, Docker, or from source.
2. **[Install the Godot addon](getting-started-addon.md)** — from the [Godot Asset Store](https://store.godotengine.org/asset/john-d-studios/godot-editor-mcp-addon/) (**Godot Editor MCP - Addon**), or copy it in; then enable it.
3. **[Configure your client](getting-started-clients.md)** — OpenCode, Claude, or any MCP host.
4. **[Install the skills](reference-skills.md)** — this is what makes your assistant enable toolsets on its own, read the honesty fields, and avoid the common Godot pitfalls. Do it before your first session.
5. **[Run your first session](getting-started-first-session.md)** — the orient → enable → preview → act → verify rhythm.

Running several clients against one editor, or driving Godot remotely? See
**[Remote & multi-client](getting-started-openwebui.md)**.

## Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **Godot** | 4.4 | 4.7 (validated target) |
| **Python** | 3.11 | 3.13 |
| **Package manager** | [uv](https://docs.astral.sh/uv/) | uv |
| **OS** | macOS / Linux / Windows | Any desktop |

::: info Godot 4.4 is the floor
The addon checks the editor version on enable and warns if it's older. A few toolsets
(`scene_edit`, `input_map`, `tilemap`, `scene_3d`) are version-gated and refuse to
enable on older editors.
:::

New to the ideas behind any of this? **[Concepts](concepts.md)** explains the mental
model in five short ideas.
