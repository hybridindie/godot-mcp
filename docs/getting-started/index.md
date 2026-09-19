---
title: Getting started
description: Install, connect, and drive your first Godot session through MCP.
---

# Getting started

Four steps, then you're driving the editor from an agent:

1. [Install the MCP server](install.md) — PyPI, Docker, or from source.
2. [Install the Godot addon](addon.md) — copy it into your project, enable it.
3. [Configure your MCP client](clients.md) — OpenCode, Claude, or any MCP host.
4. [Run your first session](first-session.md) — inspect, then mutate, then verify.

Remote / multi-machine setups (OpenWebUI, Docker, HTTP transport) are covered
in [remote access](openwebui.md).

## Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **Godot** | 4.4 | 4.7 (validated target) |
| **Python** | 3.11 | 3.13 |
| **Package manager** | [uv](https://docs.astral.sh/uv/) | uv |
| **OS** | macOS / Linux / Windows | Any desktop |

!!! note "Godot 4.4 is the floor"
    The addon checks the editor version on enable and warns if it is older.
    Some toolsets (`scene_edit`, `input_map`, `tilemap`, `scene_3d`) are
    version-gated and refuse to enable on older editors.