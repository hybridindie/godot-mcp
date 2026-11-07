---
type: index
title: "Reference"
description: "The tool surface in tables — toolsets, safety classes, value shapes, errors, and env vars."
created: 2026-09-19
updated: 2026-10-18
---

# Reference

::: info For readers who know MCP
This is the developer reference. New here and just want to make a game? → **[For creators](for-creators.md)**.
:::

Authoritative tables for the surface. The per-tool contract spec (full result
schemas, every field) remains [`docs/tool-contracts.md`](https://github.com/hybridindie/godot-mcp/blob/main/docs/tool-contracts.md)
in the repo — it is the source of truth; these pages are the readable map.

- [The compatibility contract](reference-contract.md) — what the contract covers, why it is versioned, and how negotiation works
- [Toolsets & tools](reference-toolsets.md) — every toolset, every tool
- [Safety classes](reference-safety-classes.md) — class × tool matrix, `dry_run`/`confirm` semantics
- [Value shapes](reference-value-shapes.md) — how Godot types arrive as JSON
- [Errors & recovery](reference-errors.md) — the error-code enum + the recovery table
- [Prompts & resources](reference-prompts.md) — the 9 workflow prompts + the `godot://` resources
- [Skills](reference-skills.md) — the 3 installable AI skills + the expert reference guides
- [Consumer integration](reference-consumers.md) — layering game-specific agents on top (skills, orchestrator pattern)
- [Comparison with other tools](reference-compare.md) — the other live-editor MCP servers, side by side, including where this one is not ahead
- [Env vars](reference-env-vars.md) — every configuration knob
- [Changelog](changelog.md) — what shipped in each release

::: info For LLM agents
The site serves [`llms.txt`](https://hybridindie.github.io/godot-mcp/llms.txt)
(page index) and
[`llms-full.txt`](https://hybridindie.github.io/godot-mcp/llms-full.txt)
(everything as one markdown document) — point agents at those instead of
crawling HTML.
:::
