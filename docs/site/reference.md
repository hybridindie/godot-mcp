---
type: index
title: "Reference"
description: "The tool surface in tables — toolsets, safety classes, value shapes, errors, and env vars."
created: 2026-09-19
updated: 2026-09-19
---

# Reference

Authoritative tables for the surface. The per-tool contract spec (full result
schemas, every field) remains [`docs/tool-contracts.md`](https://github.com/hybridindie/godot-mcp/blob/main/docs/tool-contracts.md)
in the repo — it is the source of truth; these pages are the readable map.

- [Toolsets & tools](reference-toolsets.md) — every toolset, every tool
- [Safety classes](reference-safety-classes.md) — class × tool matrix, `dry_run`/`confirm` semantics
- [Value shapes](reference-value-shapes.md) — how Godot types arrive as JSON
- [Errors & recovery](reference-errors.md) — the error-code enum + the recovery table
- [Env vars](reference-env-vars.md) — every configuration knob
- [Changelog](changelog.md) — what shipped in each release

!!! note "For LLM agents"
    The site serves [`llms.txt`](https://hybridindie.github.io/godot-mcp/llms.txt)
    (page index) and
    [`llms-full.txt`](https://hybridindie.github.io/godot-mcp/llms-full.txt)
    (everything as one markdown document) — point agents at those instead of
    crawling HTML.
