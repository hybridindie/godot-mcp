# Text Shader (.gdshader) Authoring

A text shader is a `res://*.gdshader` file (GLSL-like), wrapped in a
`ShaderMaterial` and assigned to a node. This is the `shader` toolset — the
counterpart to `visual_shader` (see `references/visual-shader.md`).

## The chain

```
create_shader → validate_shader → assign_shader_material → set_shader_param
  (write it)     (compile-check)     (bind to a node)        (tune uniforms)
```

| Tool | Purpose |
|------|---------|
| `godot_shader_create(shader_path, code)` | write/overwrite a `.gdshader` (undoable) |
| `godot_shader_validate(shader_path)` | **real headless compile** → structured errors |
| `godot_shader_assign_material(node_path, shader_path)` | make + bind a ShaderMaterial |
| `godot_shader_set_param(node_path, name, value, param_type)` | set a uniform |
| `godot_shader_get_param(node_path, name)` / `godot_shader_read(shader_path)` | read back |

## Pitfalls

- **Validate before you assign.** `godot_shader_validate` runs a genuine
  headless engine compile and returns `{message, source, line}` per error.
  Skipping it means discovering a syntax error at play time, when the node
  renders magenta/blank. This is the single highest-value step.
- **`shader_type` must match the node.** `canvas_item` for 2D Controls/Node2D,
  `spatial` for 3D materials, `particles`, `sky`, `fog`. A `spatial` shader on
  a 2D node is invalid and validates as an error.
- **`create_shader` writes to disk immediately.** It is undoable (restores the
  previous bytes / removes the file), but there is no "in-memory only" state —
  disk and editor agree.
- **Assignment picks the right slot:** `material` for CanvasItem,
  `material_override` for a GeometryInstance3D. The call reports which it set.
- **`set_shader_param` needs the uniform to exist** in the shader source
  (declared `uniform`). `get_shader_param` returns `exists=false` when it does
  not — the shader's own default applies until you set it.
- **`param_type` coerces the value** (float/int/bool/vector2/vector3/vector4/
  color). Omit it to infer: numbers/bools pass through, `[x,y,z]` → vector,
  HTML string → color. See `docs/tool-contracts.md#value-shapes`.

## Persistence truth

`assign_shader_material` and `set_shader_param` report **`persisted`**. When a
node is inside an **instanced scene without Editable Children**, the material
applies live but **will not be saved** — the result carries `persisted: false`
plus a `reason` and `hint`. A `dry_run` preview asks the addon for the same
verdict read-only, so preview and real run agree. Read `persisted`; a shader
edit that silently won't survive a save is a wasted turn.

## When to choose text vs VisualShader

Choose a **text shader** when the effect is a few lines of math, when it should
diff cleanly in git, and when compile validation matters — `validate_shader`
gives a real compiler verdict. Choose a **VisualShader** when the graph is
large or maintained visually. They are separate resource types; neither
converts to the other.

## Read-back

`godot_shader_read(shader_path)` returns the source text (byte-comparable);
`godot_shader_get_param(node_path, name)` returns the live uniform value or
`exists=false`. Snapshot the source before an overwrite if you may need to
revert.
