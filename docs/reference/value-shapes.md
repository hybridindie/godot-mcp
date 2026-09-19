---
title: Value shapes
description: How Godot types (Vector2/3, Color, Rect2, NodePath) arrive as JSON — and how they are coerced back.
---

# Value shapes

Godot values cross the bridge as JSON. The coercion lives in one addon helper
(`type_coerce.gd`) — never inline in a handler — and the same shapes work for
setting properties, batch values, and tool params.

## Accepted input shapes (JSON → Godot)

| Godot type | Accepted JSON |
|------------|---------------|
| `Vector2` / `Vector3` | `{"x":1,"y":2}` · `[1,2]` · `"Vector2(100, 200)"` |
| `Color` | `{"r":1,"g":0,"b":0,"a":1}` · `"#ff0000"` |
| `Rect2` | `{"position":{...},"size":{...}}` |
| `NodePath` / `StringName` | a string |
| Primitives | as-is (`true`, `3`, `"text"`) |
| Object-typed properties | `"res://path"` or `"uid://…"` (loaded via `ResourceLoader`), or `null` to clear |

Example:

```jsonc
// set_node_property(node_path="Player", property="modulate", value="#ff8800")
{ "id": "7", "command": "cmd_set_node_property", "params": {
    "node_path": "Player", "property": "modulate", "value": "#ff8800" } }
```

## Output shapes (Godot → JSON)

The same coercion runs in reverse for every result: a `Vector2` comes back as
`{"x":…, "y":…}`, a `Color` as `{"r":…, "g":…, "b":…, "a":…}`, and so on.
Everything that crosses the bridge is JSON-safe — no Godot objects, ever
(serialized trees are `{name, type, path, script, children}` dicts; large
trees support `max_depth`).

## Coercion rules the addon follows

1. **Coerce to the property's declared type** when it already exists (a vector
   dict becomes a `Vector2`, a string form is parsed).
2. **Unknown keys are refused, not defaulted** — a malformed value is a
   `VALIDATION_ERROR` naming the property, never a silent zero (which would
   target the wrong cell/property).
3. **Type-check up front for polymorphic setters**: `setup_collision` rejects a
   2D shape on a 3D body (and vice versa) with a dimension-naming hint, instead
   of shipping collisionless levels behind `ok: true`.

## Where it lives

- Addon: `godot/addons/godot_mcp/type_coerce.gd` (`to_json` / `from_json`)
- Server: `mcp_server/coercion_middleware.py` (per-call param coercion)
- Full per-property table: `docs/tool-contracts.md` § value-shapes

The type-coercion logic is deliberately single-sourced: a copy-pasted coercion
in one handler is a drift bug the addon rules call out as blocking.