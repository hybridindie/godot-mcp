# Tool, resource & prompt contracts

The MCP surface is the product: agents call it with no human in the loop, so the types,
safety classes, and preconditions *are* the API. This document specifies that surface. The
underlying transport and envelope are in [`architecture.md`](architecture.md); the binding
rules are [`../.claude/rules/mcp-tools.md`](../.claude/rules/mcp-tools.md) and
[`../.claude/rules/error-handling.md`](../.claude/rules/error-handling.md).

> Scope note: concrete tools land from issue #5 onward. This document fixes the *shape*
> every tool/resource/prompt must take. Add each concrete contract here as it is built.

## Tools

A tool is a thin wrapper over the bridge or a service:

```
@mcp.tool()  →  validate typed args  →  check preconditions  →  bridge.send("cmd_…", params)  →  typed result
```

Every `@mcp.tool()`:

- Takes **typed** parameters (a Pydantic model or typed args) and returns a **typed**
  Pydantic model — never a raw `dict`.
- Has an **agent-facing docstring**: what it does, when to use it, what it returns.
- Validates inputs and checks preconditions **before** any side effect.
- Is **delegation only** — no domain branching in the handler body.
- Carries a `safety_class`.

### Naming

The addon handler is `cmd_<verb>_<noun>`; the matching MCP tool drops the `cmd_` prefix
(`cmd_create_node` ⇄ `create_node`). All domain/data fields are `snake_case`.

### Safety classes

Every tool is tagged with exactly one:

| Class | Meaning | Extra requirements |
|-------|---------|--------------------|
| `read_only` | Never mutates. | none |
| `mutating` | Reversible editor change (registered with `UndoRedo`). | accept `dry_run: bool = False` |
| `destructive` | Deletes/overwrites, possibly irreversible. | accept `dry_run` **and** require `confirm: bool = True` |
| `runtime` | Controls game execution. | — |

- `dry_run=True` returns what *would* happen and performs nothing.
- All safety logic lives in `mcp_server/safety.py` — **never** in the addon (issue #14).
- `list_tools_by_safety_class()` exposes the tagging for agent introspection.

### Preconditions

Checked before any mutation; a failure returns a structured `PRECONDITION_FAILED`
envelope (see [`architecture.md`](architecture.md)), never a Python exception:

- `require_bridge_connected` — the Godot addon is reachable.
- `require_active_scene` — a scene is open in the editor.
- `require_node_exists(path)` — the target node path resolves.

### Per-tool contract template

Document each tool here as it lands, using this shape:

> #### `create_node` — `mutating`
> Create a node of `node_type` as a child of `parent_path`, named `name`.
> **Preconditions:** `require_bridge_connected`, `require_active_scene`,
> `require_node_exists(parent_path)`.
> **Params:** `parent_path: str`, `node_type: str`, `name: str`, `dry_run: bool = False`.
> **Returns:** `CreateNodeResult { node_path: str, created: bool }`.
> **Bridge command:** `cmd_create_node`.

## Resources

- `@mcp.resource("godot://…")` handlers are **read-only** and return JSON strings; no side
  effects ever. Mutations always go through tools.
- Read-only project context is exposed both as tools (issue #5) and as `godot://`
  resources (issue #11); the two are kept consistent.

## Prompts

- `@mcp.prompt()` handlers are **step-numbered instruction templates** that tell the agent
  which tools/resources to use in what order. They instruct; they do not act.
- Arguments are typed and documented.
- Examples (issue #12): `create_tower`, `add_wave`, `wire_tower_attack`.

## Client fallback

Provide a `resources-as-tools` / `prompts-as-tools` fallback for MCP clients that do not
implement the resource/prompt protocols, so the full surface is reachable as plain tools.
