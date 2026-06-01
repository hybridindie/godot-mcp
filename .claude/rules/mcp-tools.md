---
paths:
  - "mcp_server/tools/**/*.py"
  - "mcp_server/resources/**/*.py"
  - "mcp_server/prompts/**/*.py"
---

# MCP Tool, Resource & Prompt Contract (Article VI + Safety Classes)

The tool surface is the API. Agents call it with no human in the loop, so the contract — types, safety, preconditions — is the product.

## Tools

Every `@mcp.tool()` MUST:
- Take typed parameters (Pydantic model or typed args) and return a typed Pydantic model — never a raw `dict`.
- Have a docstring written for an agent: what it does, when to use it, what it returns. This is the client-facing description.
- Validate inputs and check preconditions **before** any side effect.
- Be thin: route to the bridge or a service, then return. Logic lives elsewhere (see [[architecture]]).

## Safety classes (every tool is tagged)

| Class | Meaning | Extra requirements |
|-------|---------|--------------------|
| `read_only` | Never mutates | none |
| `mutating` | Reversible editor change (UndoRedo) | accept `dry_run: bool = False` |
| `destructive` | Deletes/overwrites, maybe irreversible | accept `dry_run` **and** require `confirm: bool = True` |
| `runtime` | Controls game execution | — |

MUST:
- Set a `safety_class` on every tool's metadata.
- `dry_run=True` returns what *would* happen, performs nothing.
- Keep all safety logic in `mcp_server/safety.py` — never in the addon.
- Expose `list_tools_by_safety_class()` for agent introspection.

## Preconditions

Check before mutating, and fail with a structured precondition error (see [[error-handling]]), never a Python exception:
- `require_bridge_connected` — Godot reachable.
- `require_active_scene` — a scene is open.
- `require_node_exists(path)` — target path resolves.

## Resources & prompts

- **Resources** (`@mcp.resource("godot://...")`) are read-only and return JSON strings. No side effects. Mutations always go through tools.
- **Prompts** (`@mcp.prompt()`) are step-numbered instruction templates — they tell the agent *which tools/resources to use in what order*, they do not act. Typed, documented arguments.
- Provide a `resources-as-tools` / `prompts-as-tools` fallback for clients without that protocol.

## Anti-patterns

- Returning a raw `dict` from a tool (breaks client typing).
- Side effects in a resource handler.
- A `mutating`/`destructive` tool with no `dry_run`; a `destructive` tool that proceeds without `confirm=True`.
- `print()` for logging — use structured logs (see [[error-handling]]).
