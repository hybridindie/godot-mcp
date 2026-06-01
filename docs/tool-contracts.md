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
- Tag tools with the `READ_ONLY` / `MUTATING` / `DESTRUCTIVE` / `RUNTIME` meta constants
  from `safety.py`, e.g. `@mcp.tool(meta=MUTATING)`.
- `list_tools_by_safety_class()` is a `read_only` tool returning `{ class: [tool names] }`
  for agent introspection.

#### `dry_run` / `confirm` convention (issue #14)

- `mutating` and `destructive` tools take `dry_run: bool = False`. With `dry_run=True`, the
  tool runs its preconditions and returns its typed result describing what *would* happen
  (e.g. a `created=False` / `dry_run=True` flag), **sending no mutation** over the bridge.
- `destructive` tools additionally take `confirm: bool = False` and call
  `require_confirmation(confirm, action)` — without `confirm=True` they fail with a
  `PRECONDITION_FAILED` (`required="confirm"`), never deleting anything.

### Preconditions

Checked before any side effect. Each is a function in `safety.py` that raises a typed
`PreconditionError`; the `enforce_preconditions` decorator converts it to a `ToolError`
carrying `"<ERROR_CODE>: <hint> [required=<field>]"` — a structured, actionable message,
never a Python traceback. The structured precondition shape (matching the bridge envelope):

```json
{
  "ok": false,
  "error": "PRECONDITION_FAILED",
  "hint": "No scene is currently open. Open a scene before creating nodes.",
  "required": "active_scene"
}
```

- `require_bridge_connected(bridge)` — Godot reachable (else `BRIDGE_DISCONNECTED`,
  `required="bridge_connected"`).
- `require_active_scene(bridge)` — a scene is open (`required="active_scene"`).
- `require_node_exists(bridge, path)` — the target node path resolves (else
  `RESOURCE_NOT_FOUND`, `required="node_exists"`).
- `require_confirmation(confirm, action)` — destructive guard (`required="confirm"`).

### Per-tool contract template

Document each tool here as it lands, using this shape:

> #### `create_node` — `mutating`
> Create a node of `node_type` as a child of `parent_path`, named `name`.
> **Preconditions:** `require_bridge_connected`, `require_active_scene`,
> `require_node_exists(parent_path)`.
> **Params:** `parent_path: str`, `node_type: str`, `name: str`, `dry_run: bool = False`.
> **Returns:** `CreateNodeResult { node_path: str, created: bool }`.
> **Bridge command:** `cmd_create_node`.

### Implemented tools

#### Inspection (issue #5) — all `read_only`

Every tool routes to the matching `cmd_*` addon handler and returns a typed model.
Failures surface as a `ToolError` carrying `"<ERROR_CODE>: <hint>"`. No-scene / no-selection
states return an empty model (`is_open=False` / `tree=None` / `selected=None`), not an error.

| Tool | Params | Returns | Bridge command |
|------|--------|---------|----------------|
| `get_project_info` | — | `ProjectInfo { name, godot_version, main_scene?, autoloads, input_actions }` | `cmd_get_project_info` |
| `get_active_scene` | — | `ActiveScene { is_open, path?, name? }` | `cmd_get_active_scene` |
| `get_scene_tree` | `max_depth: int = -1` | `SceneTree { tree: SceneNode? }` | `cmd_get_scene_tree` |
| `get_selected_node` | — | `SelectedNode { selected: NodeInfo? }` | `cmd_get_selected_node` |
| `get_node_properties` | `node_path: str` | `NodeInfo { node_path, type, script?, properties, children }` | `cmd_get_node_properties` |

`SceneNode = { name, type, script?, children: [SceneNode] }`. `get_node_properties` errors
with `RESOURCE_NOT_FOUND` (bad path) or `PRECONDITION_FAILED` (no scene open).

#### Safety introspection (issue #14) — `read_only`

| Tool | Params | Returns |
|------|--------|---------|
| `list_tools_by_safety_class` | — | `{ "read_only": [...], "mutating": [...], ... }` |

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
