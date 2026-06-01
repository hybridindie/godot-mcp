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

#### Mutation (issue #6) — `mutating` (except `delete_node`)

All take `dry_run: bool = False` (preview, sends no change). Each routes to a
UndoRedo-wrapped `cmd_*` handler and runs preconditions first.

| Tool | Params | Returns | Class |
|------|--------|---------|-------|
| `create_node` | `parent_path, node_type, node_name` | `CreateNodeResult { node_path, created }` | `mutating` |
| `rename_node` | `node_path, new_name` | `RenameNodeResult { node_path, old_name?, new_name, renamed }` | `mutating` |
| `set_node_property` | `node_path, property, value` | `SetPropertyResult { node_path, property, value, set }` | `mutating` |
| `delete_node` | `node_path, confirm=False` | `DeleteNodeResult { node_path, deleted }` | **`destructive`** |
| `attach_script` | `node_path, script_path` | `AttachScriptResult { node_path, script_path, attached }` | `mutating` |
| `connect_signal` | `source_path, signal_name, target_path, method_name` | `ConnectSignalResult { …, connected }` | `mutating` |
| `save_scene` | — | `SaveSceneResult { path?, saved }` | `mutating` |
| `create_scene` | `root_type, scene_path` | `CreateSceneResult { scene_path, root_type, created }` | `mutating` |

- `set_node_property` coerces JSON to the property's declared Godot type via
  `type_coerce.from_json` (Vector2/3 & Color as `{…}` objects or arrays, NodePath as string,
  plus string forms like `"Vector2(100, 200)"` and `"#ff0000"` — issue #51).
- `delete_node` (destructive) requires `confirm=True` to delete; `dry_run=True` previews
  without confirming. The addon also honors the `confirm` flag defensively.
- `create_scene` writes a new `.tscn`/`.scn` and opens it; it is a file creation, not a
  UndoRedo-tracked tree edit.

Node parity (issue #31), also in `scene_edit`:

| Tool | Params | Returns | Class |
|------|--------|---------|-------|
| `duplicate_node` | `node_path` | `DuplicateNodeResult { node_path, source_path }` | `mutating` |
| `move_node` | `node_path, new_parent_path, index=-1` | `MoveNodeResult { node_path, moved }` | `mutating` |
| `add_to_group` / `remove_from_group` | `node_path, group` | `GroupResult { node_path, group, in_group, changed }` | `mutating` |
| `list_signal_connections` | `node_path` | `SignalConnectionList { node_path, connections: [{signal, target_path, method, persistent}] }` | `read_only` |
| `disconnect_signal` | `source_path, signal_name, target_path, method_name` | `DisconnectSignalResult { …, disconnected }` | `mutating` |

`duplicate_node` adds with a readable name (`Box2`). `move_node` rejects moving the root or
into a descendant. Group membership is persistent (saved into the scene). All reversible via
the editor's undo. The `mutating` tools also accept `dry_run: bool = False` and echo it in
the result (omitted from the table for brevity, per the `dry_run`/`confirm` convention above).

#### Scripts (issue #10) — category: `scripts` (gated off by default)

Read/write/patch route through the addon (single path; the editor re-scans after
writes, and writes register `UndoRedo`). `get_parse_errors` shells out to
`godot --check-only` (Godot has no in-editor API for structured parse errors).

| Tool | Params | Returns | Class |
|------|--------|---------|-------|
| `read_script` | `script_path` | `ScriptContent { script_path, content }` | `read_only` |
| `list_scripts` | `directory = "res://"` | `ScriptList { directory, scripts[] }` (recursive) | `read_only` |
| `get_script_for_node` | `node_path = ""` (else selected) | `NodeScript { node_path, script_path?, content? }` | `read_only` |
| `write_script` | `script_path, content, dry_run=False` | `WriteScriptResult { script_path, created, dry_run }` | `mutating` |
| `patch_script` | `script_path, find, replace, dry_run=False` | `PatchScriptResult { script_path, replacements, dry_run }` | `mutating` |
| `get_parse_errors` | `script_path` | `ParseCheckResult { script_path, ok, errors: [ParseError{message, source?, line?}] }` | `read_only` |

Non-`.gd` paths, missing files, and a `find` string that isn't present return structured
errors. `write_script`/`patch_script` are reversible via the editor's undo.

#### Runtime (issue #13) — `runtime` (category: `runtime`, gated off by default)

| Tool | Params | Returns |
|------|--------|---------|
| `run_and_capture` | `scene?: str`, `timeout_seconds: int = 10` | `RunCaptureResult { ran, exit_code?, timed_out, duration_seconds, errors[], warnings[], output[], command }` |

Runs the project headless (optionally a specific `scene`), waits up to the timeout,
and returns a structured summary. `errors`/`warnings` are `LogEntry { type, message,
source?, line? }` parsed from stdout/stderr. Project directory is resolved from
`GODOT_MCP_PROJECT_DIR` else the connected editor's project; the Godot binary from
`GODOT_MCP_GODOT_BIN` else `PATH`/known locations (missing binary → structured error).
Enable with `enable_toolset("runtime")`. Launches a Godot process directly (see the
runtime-execution note in [`architecture.md`](architecture.md)).

#### Safety introspection (issue #14) — `read_only`

| Tool | Params | Returns |
|------|--------|---------|
| `list_tools_by_safety_class` | — | `{ "read_only": [...], "mutating": [...], ... }` |

#### Toolset gating (issue #26) — `read_only` (category: `core`)

To keep the exposed surface small, tools are grouped into **categories** (`core`,
`inspection`, `scene_edit`, …). `core` is always on; the default exposure is
`core` + `inspection`. Other categories (starting with `scene_edit`) are gated off
until enabled. These meta-tools are always available:

| Tool | Params | Returns | Notes |
|------|--------|---------|-------|
| `list_toolsets` | — | `[ToolsetInfo { name, enabled, description }]` | discover categories |
| `enable_toolset` | `category` | `ToolsetInfo` | expose a category's tools (fires `list_changed`) |
| `disable_toolset` | `category` | `ToolsetInfo` | hide a category again |

`enable_toolset`/`disable_toolset` reject unknown categories and `core` with a
structured `ToolError`. They change tool *exposure* only — never the Godot project
— so they are `read_only`. The default-off-for-new-categories rule means the live
surface stays small as the catalog grows (see `.claude/rules/mcp-tools.md`).

## Resources

- `@mcp.resource("godot://…")` handlers are **read-only** and return JSON strings; no side
  effects ever. Mutations always go through tools.
- Read-only project context is exposed both as tools (issue #5) and as `godot://`
  resources (issue #11); the two are kept consistent.

### Implemented resources (issue #11)

Addressable, refreshed-on-access snapshots. Each returns a JSON string; on a bridge
failure it returns valid JSON carrying the structured error (`{ "error", "hint" }`).

| URI | Content | Bridge command |
|-----|---------|----------------|
| `godot://project/info` | project name, Godot version, main scene, autoloads, input actions | `cmd_get_project_info` |
| `godot://scene/current` | open scene `{ is_open, path, name }` | `cmd_get_active_scene` |
| `godot://scene/tree` | full scene tree (may be large) | `cmd_get_scene_tree` (`max_depth=-1`) |
| `godot://scene/tree/{max_depth}` | scene tree limited to N child levels (template) | `cmd_get_scene_tree` |
| `godot://node/selected` | selected node snapshot, or `{ "selected": null }` | `cmd_get_selected_node` |

**Fallback:** `read_resource(uri)` is a `core` `read_only` tool that returns any of the
above by URI — for clients without resource-protocol support. Unknown URIs return a
structured `ToolError`.

Game-specific resources from the original issue (`godot://game/towers|enemies|waves|domain`)
are **out of scope** here — they depend on a game's domain model and belong to the
separate game project.

## Prompts

- `@mcp.prompt()` handlers are **step-numbered instruction templates** that tell the agent
  which tools/resources to use in what order. They instruct; they do not act.
- Arguments are typed and documented.
- Prompts here stay **game-agnostic** — generic Godot workflows (e.g. "create a scene with
  a typed root", "wire a signal"). Game-specific prompts belong to the separate game project.

## Client fallback

Provide a `resources-as-tools` / `prompts-as-tools` fallback for MCP clients that do not
implement the resource/prompt protocols, so the full surface is reachable as plain tools.
