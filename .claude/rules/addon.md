---
paths:
  - "godot/addons/godot_mcp/**/*.gd"
---

# Godot Addon (GDScript) Conventions

The addon is the only code that touches the Godot Editor API. Target **Godot 4.4+**. It receives JSON command envelopes (see [[error-handling]]) and dispatches them to handlers.

## Always verify against current Godot docs

Godot 4.x changes editor and engine APIs between minor releases, and model training data lags behind. Before relying on any Godot class, method, signal, or `EditorPlugin` / `EditorInterface` / `EditorUndoRedoManager` / `WebSocketPeer` behavior:

MUST:
- Confirm the signature against the **current official docs for the project's Godot version** (`docs.godotengine.org` — match the version, not "latest" if they differ) rather than from memory.
- Prefer the `context7` MCP server to fetch up-to-date Godot documentation on demand; fall back to the official docs site. Do this even for APIs you think you know.
- When an API was renamed/removed across versions (common from 3.x → 4.x and across 4.x minors), use the form that matches our pinned version and note the version in a comment if it's non-obvious.

ANTI-PATTERN: writing GDScript against a remembered 3.x or early-4.x API without checking it still exists in the target version.

## Plugin & structure

MUST:
- All addon scripts carry `@tool`. The entry script extends `EditorPlugin`.
- `_enter_tree()` / `_exit_tree()` set up and tear down cleanly — enabling/disabling the plugin never crashes or leaks the editor.
- A `TCPServer` + `WebSocketPeer` accepts the local server connection; incoming envelopes go through a single **command router** to handlers.
- Command handlers are named `cmd_<verb>_<noun>` (the matching MCP tool drops the `cmd_` prefix). One handler does one thing.
- The status dock is **read-only** — it reflects connection state, project/scene/selected-node, and a recent-command log. It never mutates the project.

## Mutations

MUST:
- Wrap every create / rename / delete / set-property in `EditorUndoRedoManager` so the human can undo agent actions.
- `cmd_delete_node` and other destructive handlers honor the `confirm` flag passed from the server (the safety class is enforced server-side; see [[mcp-tools]]).
- Report the concrete result (e.g. the saved file path) in the response `result`.

## Serialization & types

MUST:
- Everything returned to the server is **JSON-safe** — no Godot objects. Scene trees serialize to `{ name, type, script, children }` and support a `max_depth`.
- Coerce Godot types (`Vector2/3`, `Color`, `Rect2`, `NodePath`) to/from JSON in a dedicated `type_coerce.gd` helper — never inline, never duplicated.

## Anti-patterns

- A handler that mutates without registering UndoRedo.
- Returning a Godot object or a non-serializable value across the bridge.
- Type-coercion logic copy-pasted across handlers instead of living in `type_coerce.gd`.
- Letting a GDScript error propagate as a raw trace instead of an `ok: false` envelope.
- Blocking the editor thread on a long operation in a handler.
