# AGENTS.md

Entry point for OpenCode and other agentic clients working in **godot-mcp**.

## Independent & harness-agnostic

godot-mcp is a **standalone MCP server** — generic Godot editor control over the Model Context Protocol. It is usable by **any** AI agent harness (Claude Code, OpenCode, or any MCP client over stdio or Streamable HTTP) and is **game-agnostic** (no built-in game vocabulary; see [`CLAUDE.md`](./CLAUDE.md)).

It has **no dependency on any specific consumer.** Other projects depend on godot-mcp, never the reverse — e.g. the `godot-agents` orchestrator is coded specifically against this server's tool surface, but godot-mcp must **never** couple back to it (no agent-harness-specific tools, prompts, assumptions, or imports). Keep the surface generic; let consumers adapt to it.

The full project context and the grounding-rule index are in [`CLAUDE.md`](./CLAUDE.md) — read it first. The constitutional rules themselves live in [`.claude/rules/`](./.claude/rules/) and are the source of truth for how to build here:

- `architecture.md` — library-first; the addon/server boundary
- `mcp-tools.md` — tool/resource/prompt contract; safety classes, `dry_run`/`confirm`
- `error-handling.md` — the versioned JSON envelope; structured errors
- `async-patterns.md` — async FastMCP; bridge timeouts, reconnect, `id` correlation
- `addon.md` — GDScript addon conventions (`@tool`, UndoRedo, serialization)
- `testing.md` — TDD mandate; suite health
- `workflow.md` — issue → red test → green → preflight → PR → merge
- `enforcement.md` — gates, PR checklist, versioning

These rules are path-scoped; apply the one(s) matching the files you touch. When a rule and this file disagree, the rule wins.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
