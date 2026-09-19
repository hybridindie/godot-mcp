---
type: index
title: "Consumer integration"
description: "Layering game-specific agents on godot-mcp — the skills, the godot-agents orchestrator, and the eval harness."
created: 2026-09-19
updated: 2026-09-19
---

# Consumer integration

godot-mcp is deliberately game-agnostic. This page maps the integration
surface for consumers that layer game-specific behavior on top.

## The integration surface

A consumer pins four things (all versioned, all additive since contract 1):

| Pinned surface | Where it lives | How to track drift |
|----------------|----------------|--------------------|
| Tool names + param keys | `_TOOL_NAMES` in the consumer's MCP client | mirror verbatim; tool-accuracy evals double as contract checks |
| Toolset categories | `enable_toolset(category)` before gated calls | server-global set — a grant survives reconnects |
| Envelope/result shapes | normalized `MCPResult(ok, data, error, required)` | `structuredContent` preferred when present |
| Contract version | `godot_get_server_info.contract_version` | client compatible when `min ≤ client ≤ contract` |

## The companion skills (in this repo)

Three installable AI skills ship under
[`skills/`](https://github.com/hybridindie/godot-mcp/tree/main/skills) —
install into any client via `scripts/install-skills.sh`:

- `godot-getting-started` — bridge connection, toolset gating, safety classes,
  honesty fields, round-trip economy
- `godot-playtest-and-debug` — runtime play-test, input simulation,
  break-state gate, timeout semantics
- `godot-expert` — Godot 4.x engine knowledge: 10 sections + 7 reference
  guides + 11 documented bugs

They are pinned to the live surface by `tests/unit/test_skills_metadata.py`
(every tool reference must resolve, the toolset map must cover all toolsets),
so a surface change without a skills update fails the suite.

## The godot-agents orchestrator

[hybridindie/godot-agents](https://github.com/hybridindie/godot-agents) is a
LangGraph-based multi-agent system **built specifically against this server**
(not a generic MCP client). It demonstrates the consumer pattern:

- Typed client wrappers mirroring godot-mcp's tools verbatim, with the same
  param keys and `_ensure_or_return_error` gating
- Honesty-field awareness: `persisted`, `undoable`, `aborted_at`,
  `rescan_pending`, `expected_timeout`, `game_not_breaked`
- `notifications/tools/list_changed` handling (`toolset_generation`)
- An eval harness (`godot_agent_harness`) whose live suites drive a real
  editor through the bridge — the drift catcher between the two repos

## Layering your own game vocabulary

The recommended shape for a game-specific consumer:

1. **Keep godot-mcp untouched** — it stays generic; game vocabulary ("spawn
   wave", "upgrade tower") lives in your project.
2. **Wrap, don't fork** — typed client wrappers per tool group, with your
   domain models built from godot-mcp's `structuredContent` payloads.
3. **Add your own prompts/skills** — the recipe templates here
   ([prompts](reference-prompts.md)) are the pattern; your game's versions
   compose the same generic tools in game-shaped orders.
4. **Pin the contract** — assert `contract_version` at startup; the additive
   guarantee means unknown fields are safe to ignore.
5. **Eval the behavior** — the tool-accuracy eval pattern (score calls against
   an `expected_tools` spec) doubles as drift detection.