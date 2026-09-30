# VisualShader Graph Authoring

A `VisualShader` is a **graph resource** (`res://*.tres`), not a text shader.
You build it node-by-node and connect ports, then assign it like any material.
This is the `visual_shader` toolset.

## The graph chain

```
create_visual_shader → add_shader_node → connect_shader_nodes → set_shader_node_param
   (the .tres)           (a box)           (wire output→input)      (tune a value)
```

| Step | Tool | Notes |
|------|------|-------|
| 1 | `godot_visual_shader_create(name, type="3d")` | type is `2d`/`3d`/`particles`/`sky`/`fog` |
| 2 | `godot_visual_shader_add_node(shader_path, node_type, node_id, position=[x,y])` | **you choose `node_id`** |
| 3 | `godot_visual_shader_connect_nodes(shader_path, from_node, from_port, to_node, to_port)` | integer port indices |
| 4 | `godot_visual_shader_set_node_param(shader_path, node_id, property, value)` | value JSON-coerced |
| — | `godot_visual_shader_read(shader_path)` | read the graph back (nodes + connections) |
| — | `godot_visual_shader_list_node_types()` | the valid `node_type` names |

## Pitfalls

- **There is no auto-node-id.** Unlike a scene, the graph does not assign ids —
  *you* pick an integer `node_id` per node and reuse it in every connect/param
  call. Duplicate ids collide; plan a scheme (100, 110, 120…).
- **Ports are indices, not names.** `from_port`/`to_port` are the 0-based
  socket numbers on the node. Read the graph back after wiring to confirm the
  edges landed — a wrong index wires the wrong socket silently.
- **The output node is special.** Every VisualShader has exactly one output
  node; connect your final color/position into it, or the shader renders
  nothing. Its `node_type` differs per shader type (fragment output, etc.) —
  confirm with `list_node_types`.
- **`type` must match the material slot.** A `2d` graph assigned to a 3D
  material (or vice versa) is invalid. Match the graph type to where it binds.
- **Values coerce by the property's declared type.** Set a `Color` as
  `"#ff0000"` or `{"r":1,"g":0,"b":0,"a":1}`, a Vector as `{"x":1,"y":2}` or
  `[1,2]` — same coercion contract as `set_shader_param` (see
  `docs/tool-contracts.md#value-shapes`).

## Text shader vs VisualShader

Use the **`shader`** toolset for a hand-written `.gdshader` and the
**`visual_shader`** toolset for a graph. They are different resource types and
do not convert:

| | text shader (`shader`) | VisualShader (`visual_shader`) |
|---|---|---|
| Artifact | `res://*.gdshader` (GLSL-like text) | `res://*.tres` (graph) |
| Authoring | write code | add nodes + connect ports |
| Validate | `godot_shader_validate(shader_path)` (real headless compile) | no compiler — read the graph back |
| Assign | `godot_shader_assign_material(node_path, shader_path)` | assign the ShaderMaterial normally |

**Prefer a text shader when** the effect is a few lines of math — it diffs in
git and validates by compile. **Prefer a VisualShader when** non-programmers
maintain it or it is a large node graph.

For text shaders, `godot_shader_validate` runs a genuine headless compile and
returns structured errors — always run it after `create_shader` before
assigning, rather than discovering a syntax error at play time.

## Read-back

`godot_visual_shader_read(shader_path)` returns the graph (nodes with their
params, plus connections) — the inverse of the authoring calls. Snapshot it
before an edit for rollback, exactly as you would a scene.
