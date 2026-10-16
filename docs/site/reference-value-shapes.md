---
type: index
title: "Value shapes"
description: "How Godot types (Vector2/3, Color, Rect2, NodePath) arrive as JSON — and how they are coerced back."
created: 2026-09-19
updated: 2026-09-23
---

# Value shapes

Godot values cross the bridge as JSON. The coercion lives in one addon helper
(`type_coerce.gd`) — never inline in a handler — and the same shapes work for
setting properties, batch values, and tool params.

## Accepted input shapes (JSON → Godot)

| Godot type | Accepted JSON |
|------------|---------------|
| `Vector2` / `Vector3` | `{"x":1,"y":2}` · `[1,2]` · `"Vector2(100, 200)"` |
| `Vector4` | `{"x":…,"y":…,"z":…,"w":…}` · `[1,2,3,4]` · `"Vector4(1, 2, 3, 4)"` |
| `Color` | `{"r":1,"g":0,"b":0,"a":1}` · `"#ff0000"` |
| `Rect2` | `{"position":{…},"size":{…}}` |
| `Quaternion` | `{"x":…,"y":…,"z":…,"w":…}` · `"Quaternion(…)"` |
| `AABB` | `{"position":{x,y,z},"size":{x,y,z}}` · `"AABB(…)"` |
| `Plane` | `{"normal":{x,y,z},"d":…}` · `"Plane(…)"` |
| `Basis` | `{"x":{x,y,z},"y":{…},"z":{…}}` · `"Basis(…)"` |
| `Transform2D` | `{"x":{x,y},"y":{x,y},"origin":{x,y}}` · `"Transform2D(…)"` |
| `Transform3D` | `{"basis":{…},"origin":{x,y,z}}` · `"Transform3D(…)"` |
| `Projection` | `{"x":{x,y,z,w},"y":{…},"z":{…},"w":{…}}` · `"Projection(…)"` |
| `PackedByteArray` | `[0,1,255]` |
| `PackedVector2Array` / `PackedVector3Array` / `PackedColorArray` | `[{…}]` (element shape as above) |
| `NodePath` / `StringName` | a string |
| Primitives | as-is (`true`, `3`, `"text"`) |
| Non-finite floats | `"__nan__"` · `"__inf__"` · `"__-inf__"` (see below) |
| Object-typed properties | `"res://path"` or `"uid://…"` (loaded via `ResourceLoader`), or `null` to clear |

Example:

```jsonc
// set_node_property(node_path="Player", property="modulate", value="#ff8800")
{ "id": "7", "command": "cmd_set_node_property", "params": {
    "node_path": "Player", "property": "modulate", "value": "#ff8800" } }
```

## Output shapes (Godot → JSON)

The same coercion runs in reverse for every result: a `Vector2` comes back as
`{"x":…, "y":…}`, a `Color` as `{"r":…, "g":…, "b":…, "a":…}`, a `Transform3D`
as `{"basis":{…},"origin":{…}}`, and so on (the full set is the "Accepted JSON"
table above). Everything that crosses the bridge is JSON-safe — no Godot
objects, ever (serialized trees are `{name, type, path, script, children}`
dicts; large trees support `max_depth`). The **runtime probe reuses this same
module** (`type_coerce.gd`), so the editor and the running game emit identical
shapes — there is no second coercion implementation.

### Non-finite floats

JSON has no literal for `NaN`/`INF`, and `JSON.stringify` maps them lossily
(`NaN`→`null`, `INF`→`1e99999`). They are therefore encoded as explicit string
sentinels — `"__nan__"`, `"__inf__"`, `"__-inf__"` — in both directions, so a
round-trip is faithful (#641).

### Writes are verified by read-back

`set_node_property` coerces the value to the property's declared type, applies
it, then compares the **value read back** to the coerced value; a mismatch
fails with a structured `VALIDATION_ERROR` naming the expected type. A value the
engine silently ignores (an unsupported type, a dimension mismatch) can no
longer come back as the *old* value under `set: true` (#641). Group / category /
subgroup headings are rejected as properties (they have no backing storage).

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

The type-coercion logic is deliberately single-sourced — a copy-pasted coercion
layer (or one living inline in a handler) is a drift bug the addon rules call
out as blocking, and would drift from this table within weeks. It is pinned by
a headless behavior test (`godot/tests/type_coerce_smoke.gd`, wired into pytest
via `tests/integration/test_addon_read_smokes.py`) that round-trips every shape
in this document against the real Godot runtime.