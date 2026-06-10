# Tool, resource & prompt contracts

The MCP surface is the product: agents call it with no human in the loop, so the types,
safety classes, and preconditions *are* the API. This document specifies that surface. The
underlying transport and envelope are in [`architecture.md`](architecture.md); the binding
rules are [`../.claude/rules/mcp-tools.md`](../.claude/rules/mcp-tools.md) and
[`../.claude/rules/error-handling.md`](../.claude/rules/error-handling.md).

> **For user-facing setup instructions, see [`README.md`](../README.md).** This document is the
> authoritative per-tool reference for implementers and agents.

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

#### Version gating (per-toolset)

Some toolsets depend on Godot editor APIs that are only reliable from a specific
version onward (e.g. `input_map` needs `ProjectSettings.save()` to persist input
actions, which is only fully reliable from 4.4+).

`enable_toolset` checks the connected Godot version **lazily** (once per session
via `cmd_get_project_info`) against `TOOLSET_MIN_GODOT` in `mcp_server/toolsets.py`:

- `list_toolsets` surfaces `min_godot: "4.4" | null` per toolset so the agent
  knows the requirement before attempting to enable it.
- `enable_toolset("input_map")` on a 4.3 editor raises a structured `ToolError`:
  ```
  PRECONDITION_FAILED: Toolset 'input_map' requires Godot 4.4+ (connected editor is 4.3). Upgrade the editor or enable a different toolset. [required=godot_version]
  ```
- If the bridge is disconnected, the gate raises `BRIDGE_DISCONNECTED: ... [required=bridge_connected]` rather than enabling blindly.
- If the version cannot be determined (query fails or response is unparseable), the gate raises `PRECONDITION_FAILED: ... [required=bridge_connected]` — failing closed rather than enabling blindly.

Only toolsets with a documented version risk are gated. The rest
(`inspection`, `scripts`, `physics`, `runtime`, etc.) are left un-gated so the agent
can try them; the addon will produce its own structured error if an API is missing.

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
| `get_node_property_list` | `node_path: str` | `NodePropertyList { node_path, type, properties[] }` | `cmd_get_node_property_list` |

`SceneNode = { name, type, script?, children: [SceneNode] }`. `get_node_properties` errors
with `RESOURCE_NOT_FOUND` (bad path) or `PRECONDITION_FAILED` (no scene open).
`get_node_property_list` returns every valid property name for a node (useful before calling
`set_node_property`).

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
 | `instance_scene` | `parent_path, scene_path, name=""` | `InstanceSceneResult { node_path, scene_path, instanced }` | `mutating` |


 - `set_node_property` coerces JSON to the property's declared Godot type via
   `type_coerce.from_json` (Vector2/3 & Color as `{…}` objects or arrays, NodePath as string,
   plus string forms like `"Vector2(100, 200)"` and `"#ff0000"` — issue #51).
 - `delete_node` (destructive) requires `confirm=True` to delete; `dry_run=True` previews
   without confirming. The addon also honors the `confirm` flag defensively.
 - `create_scene` writes a new `.tscn`/`.scn` and opens it; it is a file creation, not a
   UndoRedo-tracked tree edit.
 - `instance_scene` (issue #80) loads a `PackedScene`, instantiates with `GEN_EDIT_STATE_INSTANCE`
   (editor builds), adds it under `parent_path`, and sets owner. Reversible via undo.

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

 #### Scene session (issue #79) — category: `scene_edit` (gated off by default)

 Editor session management. `reload_scene` discards unsaved changes and is
 **`destructive`** (`confirm=True` required); the rest are `mutating` or `read_only`.

 | Tool | Params | Returns | Class |
 |------|--------|---------|-------|
 | `open_scene` | `scene_path` | `OpenSceneResult { scene_path, opened, already_open }` | `mutating` |
 | `reload_scene` | `scene_path, confirm=False` | `ReloadSceneResult { scene_path, reloaded }` | **`destructive`** |
 | `save_all_scenes` | — | `SaveAllScenesResult { saved, count }` | `mutating` |
 | `list_open_scenes` | — | `ListOpenScenesResult { scenes[{path}] }` | `read_only` |
 | `select_nodes` | `node_paths: str[]` | `SelectNodesResult { scene_path, selected[], count }` | `mutating` |

 `open_scene` uses `EditorInterface.open_scene_from_path`. `reload_scene` requires
 the scene to already be open. `select_nodes` replaces the current editor
 selection with the resolved nodes. All accept `dry_run: bool = False` (the
 destructive tool also accepts `confirm`).

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

#### Resource files & autoloads (issue #34) — category: `resources_edit` (gated off by default)

Author resource (`.tres`/`.res`) files and register autoloads. Distinct from the read-only
`godot://` resources — this is the *authoring* surface. Property values are coerced to each
property's declared Godot type.

| Tool | Params | Returns | Class |
|------|--------|---------|-------|
| `read_resource_file` | `resource_path` | `ResourceContent { resource_path, type, script?, properties }` | `read_only` |
| `create_resource` | `type, resource_path, properties?` | `CreateResourceResult { resource_path, type, created }` | `mutating` |
| `set_resource_property` | `resource_path, property, value` | `SetResourcePropertyResult { resource_path, property, value }` | `mutating` |
| `register_autoload` | `name, path` | `RegisterAutoloadResult { name, path, registered }` | `mutating` |
| `unregister_autoload` | `name` | `UnregisterAutoloadResult { name, unregistered }` | `mutating` |

`set_resource_property` is undo-reversible; `create_resource` is a file write (not undo-tracked);
`register_autoload`/`unregister_autoload` persist to project settings. Mutating tools accept
`dry_run: bool = False` and echo it in the result (sending no change when true).

#### External asset import (issue #108) — category: `asset_import` (gated off by default)

Import external files (local paths or HTTP URLs) into a Godot project and assemble PBR materials from texture channels. This is the open-source foundation for external AI content pipelines (e.g. Meshy, Tripo) without hard-coding provider-specific logic.

| Tool | Params | Returns | Class |
|------|--------|---------|-------|
| `import_asset` | `source: str`, `target_path: str`, `options?: dict` | `ImportAssetResult { imported, target_path, detected_type }` | `mutating` |
| `create_material_from_textures` | `albedo?, normal?, roughness?, metallic?, ao?, emission?, path?` | `CreateMaterialResult { material_path, created, channels_set }` | `mutating` |
| `get_import_status` | `target_path: str` | `ImportStatusResult { imported, last_modified?, type? }` | `read_only` |

`import_asset` auto-detects the Godot type from the file extension (`.png`→`Texture2D`, `.glb`→`PackedScene`, `.wav`→`AudioStreamWAV`, etc.). When `source` is an HTTP(S) URL it is downloaded via `httpx` with a 60-second timeout, then copied to `target_path` (must start with `res://`). The response is streamed to disk in 64 KiB chunks to avoid buffering the entire payload in memory. The `options` dict may contain `overwrite` (bool, default `false`) and `import_settings` (dict, e.g. `{"type": "Texture2D", "compress": "lossy"}`). The editor filesystem scan is triggered after copy so Godot imports the file.

`create_material_from_textures` creates a `StandardMaterial3D`, assigns every non-empty texture channel that exists in the project, and saves the material as a `.tres`. The default `path` is `res://materials/generated_{rand}.tres`. Only channels with a valid `res://` texture path are included in `channels_set`. Both mutating tools accept `dry_run: bool = False` and echo it in the result (sending no change when true).

`get_import_status` checks whether the target file has an `.import` sidecar (the canonical signal that Godot has processed it) and reads the `remap/type` metadata from that sidecar. When the sidecar is missing, it falls back to `ResourceLoader.exists(target_path)` and type detection from the file extension.

#### Project & filesystem (issue #32) — category: `project` (gated off by default)

| Tool | Params | Returns | Class |
|------|--------|---------|-------|
| `get_filesystem_tree` | `directory="res://", max_depth=-1` | `FilesystemTree { tree: FsEntry{name,path,type,children} }` | `read_only` |
| `search_files` | `directory="res://", name_glob="", content="", max_results=200` | `SearchResult { matches[], truncated }` | `read_only` |
| `get_setting` | `name` | `SettingValue { name, value, exists }` | `read_only` |
| `set_setting` | `name, value, dry_run=False` | `SetSettingResult { name, value, set, dry_run }` | `mutating` |
| `resolve_uid` | `value` (a `res://` path or `uid://…`) | `UidResolution { uid?, path? }` | `read_only` |

Hidden entries (`.godot`, `.git`, …) are skipped. `search_files` matches `name_glob`
and/or `content` substring (truncating at `max_results`). `set_setting` coerces to the
setting's existing type, persists to project settings (not undo-tracked), and accepts
`dry_run`. `resolve_uid` picks direction by the input prefix.

#### Editor screenshots (issue #33) — category: `editor` (gated off by default)

| Tool | Params | Returns | Class |
|------|--------|---------|-------|
| `capture_editor_screenshot` | — | image content (PNG) | `read_only` |

The addon captures the editor viewport and returns a base64 PNG; the tool decodes it
into a FastMCP `Image` so a vision-capable client receives an image block (no temp
files). Returns a structured `INTERNAL_ERROR` if no frame is available (e.g. headless,
no display).

#### Physics (issue #41) — category: `physics` (gated off by default)

Generic over 2D/3D — pass the Godot type names. All `mutating` (UndoRedo-wrapped), `dry_run`.

| Tool | Params | Returns |
|------|--------|---------|
| `setup_physics_body` | `node_path, properties` | `SetupBodyResult { node_path, properties }` |
| `setup_collision` | `node_path, shape_type, collision_node_type="CollisionShape2D", properties?` | `CollisionShapeResult { node_path, shape_type, created }` |
| `set_physics_layers` | `node_path, layers?, mask?` (1-based bit indices) | `PhysicsLayersResult { node_path, collision_layer, collision_mask }` |
| `add_raycast` | `parent_path, name="RayCast", raycast_type="RayCast2D", properties?` | `RaycastResult { node_path, created }` |

`setup_physics_body`/`set_physics_layers` require a `CollisionObject2D`/`3D` target.
`setup_collision` creates a `CollisionShape` holding a `shape_type` shape with `properties`
(size/radius). `set_physics_layers` turns `[1,3]` into the bitmask `5`.

#### Animation (issue #39) — category: `animation` (gated off by default)

Author AnimationPlayer animations and AnimationTree graphs. All `mutating`
(UndoRedo-wrapped), `dry_run`.

| Tool | Params | Returns |
|------|--------|---------|
| `create_animation` | `node_path, name, length=1.0` | `CreateAnimationResult { player_path, animation, length }` |
| `add_animation_track` | `node_path, animation, track_path, track_type="value"` | `AnimationTrackResult { animation, track, track_path }` |
| `insert_keyframe` | `node_path, animation, track, time, value, easing=1.0` | `KeyframeResult { animation, track, time }` |
| `create_animation_tree` | `parent_path, name="AnimationTree", anim_player?, root_type="AnimationNodeStateMachine"` | `AnimationTreeResult { node_path, root_type }` |
| `add_state_machine_state` | `tree_path, state_name, animation?` | `StateMachineStateResult { tree_path, state }` |
| `set_blend_tree_node` | `tree_path, node_name, node_type` | `BlendTreeNodeResult { tree_path, node, node_type }` |

`create_animation` adds a default `AnimationLibrary` ("") if absent and rejects a
duplicate name. `add_animation_track` returns the new track index; `track_type` is one
of value/position_3d/rotation_3d/scale_3d/method/bezier/audio/animation. `insert_keyframe`
accepts Godot string forms for `value` (e.g. `"Vector2(10, 20)"`, coerced via `str_to_var`).
`add_state_machine_state` requires an `AnimationNodeStateMachine` root; `set_blend_tree_node`
requires an `AnimationNodeBlendTree` root and an `AnimationNode` `node_type`.

#### 3D scene (issue #40) — category: `scene_3d` (gated off by default)

Build 3D scenes — generic Godot, pass the node/resource type names. All `mutating`
(UndoRedo-wrapped), `dry_run`.

| Tool | Params | Returns |
|------|--------|---------|
| `add_mesh_instance` | `parent_path, mesh_type="BoxMesh", name="MeshInstance3D", properties?` | `MeshInstanceResult { node_path, mesh_type, created }` |
| `setup_camera` | `parent_path, name="Camera3D", make_current=True, properties?` | `CameraResult { node_path, current, created }` |
| `setup_lighting` | `parent_path, light_type="DirectionalLight3D", name?, properties?` | `LightResult { node_path, light_type, created }` |
| `setup_environment` | `parent_path, name="WorldEnvironment", properties?` | `EnvironmentResult { node_path, created }` |
| `gridmap_set_cell` | `node_path, position=[x,y,z], item, orientation=0` | `GridMapCellResult { node_path, position, item }` |

`add_mesh_instance` creates a `MeshInstance3D` holding a `mesh_type` primitive mesh
(BoxMesh/SphereMesh/…) configured with `properties` (size/radius/…). `setup_lighting`
requires a `Light3D` subclass (DirectionalLight3D/OmniLight3D/SpotLight3D);
`setup_environment` attaches a `WorldEnvironment` with a new `Environment` resource
configured from `properties` (background_mode, ambient_light_color, …). `gridmap_set_cell`
requires a `GridMap` with a `mesh_library` (else a structured `mesh_library` precondition);
a negative `item` clears the cell.

#### MeshLibrary authoring (issue #83) — category: `scene_3d` (gated off by default)

Build the MeshLibrary that `gridmap_set_cell` references — without one, a GridMap has
nothing to place. Target a MeshLibrary by `node_path` (an in-scene GridMap,
UndoRedo-wrapped) or `library_path` (a saved `.tres`, re-saved via ResourceSaver). All
`mutating`, `dry_run`.

| Tool | Params | Returns |
|------|--------|---------|
| `create_mesh_library` | `node_path="", save_path=""` | `MeshLibraryResult { node_path, library_path, created }` |
| `add_mesh_library_item` | `node_path="", library_path="", mesh_type="", mesh_path="", item_id?, name="", properties?` | `MeshLibraryItemResult { node_path, library_path, item_id, name, mesh_type, mesh_path }` |

Typical chain: `create_mesh_library` (assign to a GridMap and/or save a `.tres`) →
`add_mesh_library_item` (returns the `item_id`) → `gridmap_set_cell` with that `item_id`.
For `create_mesh_library` pass at least one of `node_path`/`save_path` (combinable). For
`add_mesh_library_item` pass exactly one target (`node_path`|`library_path`) and exactly
one mesh source: `mesh_type` (a primitive like BoxMesh, configured via `properties` — no
asset needed, good for greyboxing) or `mesh_path` (an imported Mesh resource
`.tres`/`.res`/`.obj`; `.glb`/`.gltf` import as scenes, not meshes). `item_id` overrides
the auto-assigned id.

#### Particles (issue #42) — category: `particles` (gated off by default)

Create and configure GPU particle systems — generic Godot, pass the node type names.
All `mutating` (UndoRedo-wrapped), `dry_run`.

| Tool | Params | Returns |
|------|--------|---------|
| `create_particles` | `parent_path, particles_type="GPUParticles2D", name?, amount=8, lifetime=1.0, properties?` | `CreateParticlesResult { node_path, particles_type, created }` |
| `set_particle_material` | `node_path, properties` | `ParticleMaterialResult { node_path, properties }` |
| `set_particle_color_gradient` | `node_path, colors[], offsets?` | `ParticleGradientResult { node_path, stops }` |
| `apply_particle_preset` | `node_path, preset` | `ParticlePresetResult { node_path, preset }` |

`create_particles` adds a GPUParticles2D/3D with a fresh ParticleProcessMaterial.
`set_particle_material` applies process-material properties (`gravity`,
`initial_velocity_min`/`max`, `scale_min`/`max`, `spread`, `color`, …), creating the
material if absent. `set_particle_color_gradient` builds a GradientTexture1D from
`colors` (HTML strings like `#ff8800` or `[r,g,b,a]`) at `offsets` (0..1, evenly
spaced if omitted) and assigns it to `color_ramp`. `apply_particle_preset` applies a
generic VFX preset — one of `fire` / `smoke` / `explosion` / `sparks` — to the node +
material + ramp in one call.

#### Navigation (issue #43) — category: `navigation` (gated off by default)

Author navigation — generic over 2D/3D, pass the node type names. All `mutating`
(UndoRedo-wrapped), `dry_run`.

| Tool | Params | Returns |
|------|--------|---------|
| `setup_navigation_region` | `parent_path, region_type="NavigationRegion2D", name?, properties?` | `NavigationRegionResult { node_path, region_type, created }` |
| `setup_navigation_agent` | `parent_path, agent_type="NavigationAgent2D", name?, properties?` | `NavigationAgentResult { node_path, agent_type, created }` |
| `bake_navigation_mesh` | `node_path` | `BakeNavigationResult { node_path, baked }` |
| `set_navigation_layers` | `node_path, layers[]` (1-based bit indices) | `NavigationLayersResult { node_path, navigation_layers }` |

`setup_navigation_region` adds a NavigationRegion2D/3D with an empty navmesh resource
assigned (NavigationPolygon for 2D, NavigationMesh for 3D) so it is ready to bake.
`setup_navigation_agent` adds a NavigationAgent2D/3D configured with `properties`
(radius, path_desired_distance, target_desired_distance, max_speed, …). `bake_navigation_mesh`
bakes the region's navmesh/navpoly synchronously (undo restores the pre-bake resource;
a region with no navmesh returns a structured precondition). `set_navigation_layers`
turns `[1,3]` into the bitmask `5` on any node with a `navigation_layers` property.

#### Audio (issue #44) — category: `audio` (gated off by default)

Set up audio — stream players, the AudioServer bus layout, and bus effects.
`get_audio_bus_layout` is `read_only`; the others are `mutating` (UndoRedo-wrapped),
`dry_run`. The bus layout is **global** AudioServer/editor state (not per-scene).

| Tool | Params | Returns |
|------|--------|---------|
| `add_audio_player` | `parent_path, player_type="AudioStreamPlayer", name?, stream_path?, properties?` | `AudioPlayerResult { node_path, player_type, created }` |
| `get_audio_bus_layout` | — | `AudioBusLayoutResult { buses[] }` (read_only) |
| `add_audio_bus` | `name, volume_db=0.0` | `AudioBusResult { index, name }` |
| `add_audio_bus_effect` | `bus, effect_type, properties?` | `AudioBusEffectResult { bus, bus_index, effect_type, effect_index }` |

`add_audio_player` creates an AudioStreamPlayer/2D/3D, optionally loading a `res://`
AudioStream (`stream_path`) and applying `properties` (volume_db, bus, autoplay, …).
`get_audio_bus_layout` returns each bus's index/name/volume_db, mute/solo/bypass, and
its effect stack. `add_audio_bus` appends a uniquely-named bus; `add_audio_bus_effect`
appends an AudioEffect (e.g. AudioEffectReverb) to the named bus.

#### TileMap (issue #45) — category: `tilemap` (gated off by default)

Edit tile cells — works with both `TileMapLayer` (current; single layer, `layer` is
ignored) and the deprecated multi-layer `TileMap` (`layer` selects the layer). Reads
are `read_only`; edits are `mutating` (UndoRedo-wrapped), `dry_run`.

| Tool | Params | Returns |
|------|--------|---------|
| `tilemap_set_cell` | `node_path, coords[x,y], source_id=-1, atlas_coords[x,y]=[0,0], alternative_tile=0, layer=0` | `TileCellResult { node_path, coords, source_id, layer }` |
| `tilemap_fill_rect` | `node_path, rect[x,y,w,h], source_id=-1, atlas_coords=[0,0], alternative_tile=0, layer=0` | `TileFillResult { node_path, rect, cells, layer }` |
| `tilemap_get_cell` | `node_path, coords[x,y], layer=0` | `TileGetResult { node_path, coords, source_id, atlas_coords, alternative_tile, empty }` (read_only) |
| `tilemap_clear` | `node_path, layer?` | `TileClearResult { node_path, layer, cleared }` |
| `tilemap_layers` | `node_path` | `TileLayersResult { node_path, node_type, layers[] }` (read_only) |

`tilemap_set_cell` sets/erases (`source_id=-1`) the cell; `tilemap_fill_rect` fills a
rectangle in one undoable action (capped at 16384 cells, returns a structured error
above that). `tilemap_clear` clears a layer (TileMap: the given layer, default 0;
TileMapLayer: the node) and reports the cell count, undo restoring the prior cells.
`tilemap_layers` lists each layer's index/name/enabled.

#### TileSet authoring (issue #82) — category: `tilemap` (gated off by default)

Build the TileSet that `tilemap_set_cell`/`tilemap_fill_rect` reference — without one,
those tools have nothing to place. Target a TileSet by `node_path` (an in-scene
TileMap/TileMapLayer, UndoRedo-wrapped) or `tileset_path` (a saved `.tres`, re-saved via
ResourceSaver). All `mutating`, `dry_run`.

| Tool | Params | Returns |
|------|--------|---------|
| `create_tileset` | `node_path="", save_path="", tile_size[w,h]=[16,16]` | `TileSetResult { node_path, tileset_path, tile_size, created }` |
| `add_tileset_atlas_source` | `texture_path, region_size[w,h], node_path="", tileset_path="", source_id?` | `TileSetSourceResult { node_path, tileset_path, source_id, texture_path, region_size }` |
| `create_tile` | `source_id, atlas_coords[x,y], node_path="", tileset_path="", size[w,h]=[1,1]` | `TileCreateResult { node_path, tileset_path, source_id, atlas_coords, size }` |

Typical chain: `create_tileset` (assign to a node and/or save a `.tres`) →
`add_tileset_atlas_source` (slice an imported `Texture2D` at `res://texture_path` into a
tile grid, returns the `source_id`) → `create_tile` (mark an atlas cell placeable). Then
`tilemap_set_cell` with that `source_id` + `atlas_coords` places a real tile.
`add_tileset_atlas_source` requires the texture to already exist in the project (it
`load`s `texture_path`); `create_tile` validates the region is inside the atlas grid and
not overlapping (`has_room_for_tile`).

#### Theme & UI (issue #46) — category: `theme_ui` (gated off by default)

Create a Theme for a Control and override theme colors, font sizes, and styleboxes on
Control nodes. All `mutating` (UndoRedo-wrapped), `dry_run`. Overrides are local to the
node and take precedence over its assigned theme.

| Tool | Params | Returns |
|------|--------|---------|
| `create_theme` | `node_path, save_path?` | `ThemeResult { node_path, theme_path, created }` |
| `set_theme_color` | `node_path, name, color` | `ThemeColorResult { node_path, name }` |
| `set_theme_font_size` | `node_path, name, size` | `ThemeFontSizeResult { node_path, name, size }` |
| `set_theme_stylebox` | `node_path, name, stylebox_type="StyleBoxFlat", properties?` | `ThemeStyleboxResult { node_path, name, stylebox_type }` |

`create_theme` makes a Theme and assigns it to the Control (saved to a `res://*.tres`
when `save_path` is given, else embedded with the scene). `set_theme_color` /
`set_theme_font_size` apply local overrides (`name` is the theme item, e.g.
"font_color", "font_size"); `color` accepts HTML strings or `[r,g,b,a]`.
`set_theme_stylebox` builds a `stylebox_type` (StyleBoxFlat/Texture/Empty/Line)
configured with `properties` (e.g. `bg_color`, `corner_radius_top_left`) and overrides
the named stylebox. Undo restores the prior override (or removes it).

#### Shaders (issue #47) — category: `shader` (gated off by default)

Author shaders — create/read `.gdshader` files, assign a ShaderMaterial, set uniforms.
`read_shader` is `read_only`; the others are `mutating` (UndoRedo-wrapped), `dry_run`.

| Tool | Params | Returns |
|------|--------|---------|
| `create_shader` | `shader_path, code=<canvas_item default>` | `ShaderResult { shader_path, created }` |
| `read_shader` | `shader_path` | `ShaderReadResult { shader_path, code }` (read_only) |
| `assign_shader_material` | `node_path, shader_path` | `ShaderMaterialResult { node_path, shader_path, material_property }` |
| `set_shader_param` | `node_path, name, value, param_type?` | `ShaderParamResult { node_path, name }` |

`create_shader` writes a `res://*.gdshader` file (undo restores the prior content or
removes it). `assign_shader_material` wraps the shader in a ShaderMaterial and assigns it
to `material` (CanvasItem) or `material_override` (GeometryInstance3D), reporting which.
`set_shader_param` sets a uniform on the node's ShaderMaterial; `param_type`
(float/int/bool/vector2/vector3/vector4/color) coerces `value`, or it is inferred
(number/bool as-is, `[x,y,z]` → vector, HTML string → color).

#### Visual shaders (issue #107) — category: `visual_shader` (gated off by default)

Create and edit VisualShader node graphs programmatically — the node-based counterpart
to the text-shader `shader` toolset (issue #47). All mutating tools support `dry_run`.

| Tool | Params | Returns | Class |
|------|--------|---------|-------|
| `create_visual_shader` | `name, type="3d", path?` | `CreateVisualShaderResult { path, created }` | `mutating` |
| `add_shader_node` | `shader_path, node_type, node_id, position=[x,y]` | `AddShaderNodeResult { node_id, node_type, added }` | `mutating` |
| `connect_shader_nodes` | `shader_path, from_node, from_port, to_node, to_port` | `ConnectShaderNodesResult { connected }` | `mutating` |
| `set_shader_node_param` | `shader_path, node_id, property, value` | `SetShaderNodeParamResult { node_id, property, value, set }` | `mutating` |
| `list_shader_node_types` | — | `ListShaderNodeTypesResult { types[] }` | `read_only` |

`create_visual_shader` creates a `VisualShader` resource with `shader_type` set from
`type` (`"2d"` → canvas_item, `"3d"` → spatial, `"particles"` | `"sky"` | `"fog"`).
`add_shader_node` instantiates a `VisualShaderNode` subclass and assigns it a graph
`position`. `connect_shader_nodes` wires an output port to an input port by
integer ids. `set_shader_node_param` sets a property on the node (values coerced via
`type_coerce`). `list_shader_node_types` scans ClassDB for instantiable
`VisualShaderNode*` classes so agents know what's available.

#### Project scaffold (issue #112) — category: `project_scaffold` (gated off by default)

Generate a project skeleton (directories, settings, autoloads, root scene) for common
game types so agents start from a known structure.  This is not a template system — it
creates empty nodes and configuration values that the agent builds on with existing tools.

| Tool | Params | Returns | Class |
|------|--------|---------|-------|
| `scaffold_project` | `type, project_name?, main_scene?, confirm=False, dry_run=False` | `ScaffoldProjectResult { created, paths_created[], autoloads_registered[] }` | **`destructive`** |

`type` is one of `2d_platformer`, `3d_fps`, `top_down_rpg`, `visual_novel`.
Requires `confirm=True` because it mutates the project filesystem broadly.
Action (when not dry-run):

1. Creates directories: `res://scenes/`, `res://scripts/`, `res://assets/`, `res://shaders/`
2. Sets project defaults: application name, viewport size, rendering method, gravity
3. Registers autoloads: `GameState` (empty Node script)
4. Creates a root scene (`Node2D` for 2D types, `Node3D` for 3D) saved as `res://scenes/{main_scene}.tscn`
5. Sets `application/run/main_scene` and persists to `project.godot`

All changes are persisted via `ProjectSettings.save()`.  The tool is `destructive`
because there is no clean UndoRedo path for broad project mutations.

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

##### Runtime session bridge (issue #66) — same `runtime` toolset

Control an editor **play session** and inspect the running game live. Unlike
`run_and_capture` (a detached headless subprocess), these play *from the editor* so the
game connects to the editor debugger, which the addon's `MCPDebugger`
(`EditorDebuggerPlugin`) captures. Live inspection requires the game to include the
**godot-mcp runtime probe** autoload (`addons/godot_mcp/mcp_runtime_probe.gd`), which
answers `godot_mcp:` debugger queries. Play control is `runtime`; reads are `read_only`.

| Tool | Params | Returns |
|------|--------|---------|
| `play_scene` | `scene_path?` | `PlayResult { playing, scene }` |
| `stop_scene` | — | `PlayResult { playing }` |
| `is_playing` | — | `PlayResult { playing, scene }` |
| `get_game_scene_tree` | — | `GameSceneTreeResult { playing, connected, tree?, hint }` (read_only) |

`play_scene` runs `scene_path` (a `res://*.tscn`) or the main scene when omitted.
`get_game_scene_tree` returns the *running* game's live tree (`GameNode { name, type,
path, children }`) from the probe; with no play session it is a `PRECONDITION_FAILED`
(`required=play_session`), and when playing without the probe it returns
`connected=false` with a `hint` to add the autoload. Replies are cached addon-side
(poll-and-cache) so the synchronous bridge stays simple. This is the foundation for
input simulation (#36) and the rest of runtime inspection (#35).

#### Input simulation (issue #36) — category: `input` (gated off by default)

Drive a *running* game — synthesize input on the #66 rails. Requires a play session +
the runtime probe; the probe calls `Input.parse_input_event` / `Input.action_press`.
Injection is `runtime`; stats are `read_only`. (Recording live input for replay is the
follow-up #68.)

| Tool | Params | Returns |
|------|--------|---------|
| `simulate_key` | `key, pressed=True, shift/ctrl/alt/meta=False` | `SimInputResult { sent, kind, count }` |
| `simulate_mouse` | `x, y, button="", pressed=True, relative_x/relative_y=0` | `SimInputResult` |
| `simulate_action` | `action, pressed=True, strength=1.0` | `SimInputResult` |
| `play_input_sequence` | `events[], delay_ms=0` | `SimInputResult { count = len(events) }` |
| `get_input_stats` | — | `InputStatsResult { playing, connected, injected }` (read_only) |
| `record_input` | `include_motion=False` | `RecordResult { recording }` |
| `stop_recording` | `timeout_ms=2000` | `RecordingResult { ready, connected, events[] }` (read_only) |

`key` is a Godot key name ("A", "Space", "Enter"). `simulate_mouse` sends motion when
`button` is empty, else a button event (left/right/middle/wheel_up/wheel_down).
`simulate_action` presses/releases an Input Map action (an action not in the *running
game's* InputMap is dropped by the probe). `play_input_sequence` replays `events` (each
`{type: key|mouse|action, …}`) `delay_ms` apart; every event's shape is validated up
front (bad `type`/missing field/unknown button → `VALIDATION_ERROR`), so `count` =
events sent. All injection requires a live probe (else `PRECONDITION_FAILED`,
`required=play_session` / `runtime_probe`). `get_input_stats.injected` is the count of
synthesized events the game has acknowledged — use it to confirm delivery.
`record_input` (issue #68) captures the input the game receives — key + mouse button, plus
mouse motion when `include_motion` — via the probe's `_input` hook; `stop_recording`
returns the buffered `events` in the same `play_input_sequence` format, so a recording
replays directly (regression). Since `parse_input_event` also fires `_input`, synthesized
input is recorded too.

#### Export (issue #50) — category: `export` (gated off by default)

Drive Godot's export pipeline. List/info are `read_only` (read `export_presets.cfg` via
the addon's `ConfigFile`); `export_project` is `runtime` (runs a Godot process, like the
runtime loop — see the note in [`architecture.md`](architecture.md)).

| Tool | Params | Returns |
|------|--------|---------|
| `list_export_presets` | — | `ExportPresetsResult { presets[], has_config }` |
| `get_export_info` | — | `ExportInfoResult { has_config, preset_count, preset_names, config_path }` |
| `export_project` | `preset, output_path, debug=False, timeout_seconds=300` | `ExportResult { exported, preset, output_path, exit_code, timed_out, duration_seconds, errors[], warnings[], output[], command }` |

`list_export_presets` returns each preset's `{index, name, platform, runnable,
export_path}`. `export_project` validates the preset name, then runs `godot --headless
--path <project> --export-release|--export-debug "<preset>" <output_path>` (relative
`output_path` resolves against the project dir) and summarizes the run — `exported` is
true when the process exits 0. **Requires export templates installed** for the target
platform (missing templates surface as errors in the result). Use a generous
`timeout_seconds`.

#### Static analysis (issue #49, #111) — category: `analysis` (gated off by default)

Project-wide static analysis, computed Python-side from the project's files (no addon
commands). All `read_only`. The project dir is resolved like the runtime loop
(`GODOT_MCP_PROJECT_DIR` else the connected editor's project; `PRECONDITION_FAILED`,
`required=project_dir` if unreachable).

| Tool | Params | Returns |
|------|--------|---------|
| `find_unused_resources` | — | `UnusedResourcesResult { unused[], scanned, referenced }` |
| `analyze_signal_flow` | `scene=""` | `SignalFlowResult { connections[], count }` |
| `detect_circular_dependencies` | — | `CircularDependenciesResult { cycles[], count }` |
| `project_stats` | — | `ProjectStatsResult { scenes, scripts, resources, total_nodes, connections, by_extension, busiest_scenes[] }` |
| `analyze_dependencies` | `resource_path` | `AnalyzeDependenciesResult { path, type, references[], referencers[] }` |
| `find_orphaned_resources` | `scan_dir="res://"`, `resource_types` | `FindOrphanedResult { orphaned[]{path, type, estimated_size}, scanned }` |
| `validate_scene_integrity` | `scene_path` | `ValidateSceneIntegrityResult { valid, errors[]{severity, message, node_path, property}, warnings[] }` |
| `cross_scene_find_refs` | `target_path` | `CrossSceneRefsResult { scenes[], resources[], scripts[] }` |

`find_unused_resources` flags resource files not referenced by any project file (excluding
entry points — the main scene, autoloads, plugin scripts). `analyze_signal_flow` parses
`[connection ...]` from scene files (each `{scene, signal, from, to, method}`).
`detect_circular_dependencies` finds cycles in the `preload`/`load`/`extends` graph among
`.gd` files. `project_stats` reports counts, total nodes, connections, a per-extension
breakdown, and the busiest scenes.

Issue #111 adds **dependency-aware** analysis: `analyze_dependencies` extracts `res://` and
`uid://` references from a resource file (recursing into sub-dependencies). `find_orphaned_resources`
surfaces resource files with no referencers, optionally filtered by Godot type and scoped to a
directory. `validate_scene_integrity` checks a scene for broken `ext_resource` paths, missing
scripts, and signal connections pointing to non-existent nodes. `cross_scene_find_refs` scans
all project files to find who references a given resource. Results remain **heuristic** text
analysis — dynamically-built paths aren't tracked, so treat them as a strong hint.

#### Batch / refactor (issue #48) — category: `batch` (gated off by default)

Operate over many nodes/scenes. Finds/deps are `read_only`; writes are `mutating`,
`dry_run`.

| Tool | Params | Returns |
|------|--------|---------|
| `find_nodes_by_type` | `node_type, parent_path=".", recursive=True` | `FindNodesResult { type, nodes[], count }` |
| `batch_set_property` | `property, value, node_paths?, node_type?, dry_run=False` | `BatchSetResult { property, applied[], skipped[], count, dry_run }` |
| `cross_scene_set_property` | `scenes[], node_type, property, value, dry_run=False` | `CrossSceneResult { results[], total_modified, scenes, dry_run }` |
| `get_dependencies` | `path` | `DependenciesResult { path, dependencies[], count }` |

`find_nodes_by_type` matches by class (incl. derived) under `parent_path` in the open
scene. `batch_set_property` sets one property on many nodes in the open scene in a single
undoable action — target by explicit `node_paths` or by `node_type`; nodes lacking the
property are reported in `skipped`. `cross_scene_set_property` edits scene **files** on
disk: it loads each (`GEN_EDIT_STATE_MAIN`), sets the property on every `node_type` node,
re-packs and saves, and re-scans — the **currently-edited** scene is skipped (its
in-memory copy would clobber the change; reported as an `error`), and each scene's
`{modified, error}` is reported so skips are explicit (this path is not UndoRedo-wrapped —
closed files). `get_dependencies` lists what a `res://` resource/scene depends on (each
`{raw, path, type}` parsed from `ResourceLoader.get_dependencies`). `dry_run` on the writes
returns the plan/counts without changing anything.

#### Debugger (issue #110, Tier 1 + Tier 2) — category: `debugger` (gated off by default)

Control breakpoints, step execution, and inspect the paused call stack in a running editor play session. Requires an active play session; `force_break` additionally needs the godot-mcp runtime probe autoload. All are `runtime`.

**Tier 1 — breakpoint control:**

| Tool | Params | Returns |
|------|--------|---------|
| `set_breakpoint` | `path (res:// script), line` | `BreakpointResult { breakpoint_set, path, line }` |
| `remove_breakpoint` | `path, line` | `BreakpointResult { breakpoint_removed, path, line }` |
| `clear_breakpoints` | — | `ClearBreakpointsResult { breakpoints_cleared }` |
| `force_break` | — | `ForceBreakResult { force_break_sent }` |

`set_breakpoint` uses `EditorDebuggerSession.set_breakpoint(path, line, true)`; `remove_breakpoint` uses `set_breakpoint(path, line, false)`. `clear_breakpoints` clears on the game side via the probe (when connected) and removes any individually tracked breakpoints on the editor side. `force_break` sets `force_break_pending = true` in the probe; the game must call `MCPRuntimeProbe.check_force_break()` in its main loop (see `docs/debugger_feasibility.md` § Limitations).

**Tier 2 — step control & stack inspection (issue #110 follow-up):**

| Tool | Params | Returns |
|------|--------|---------|
| `step_into` | — | `StepResult { stepped }` |
| `step_over` | — | `StepResult { stepped }` |
| `step_out` | — | `StepResult { stepped }` |
| `continue_execution` | — | `ContinueResult { running }` |
| `get_stack_frames` | — | `StackFramesResult { frames[] }` |
| `evaluate_expression` | `expression, frame=0` | `EvaluationResult { expression, value }` |
| `get_frame_variables` | `frame=0` | `FrameVarsResult { frame, locals[], members[], globals[] }` |

Step tools send `step`/`next`/`out`/ `continue` via `EditorDebuggerSession.send_message` and require the game to be paused (`session.is_breaked()`). `get_stack_frames` returns the current call stack from the debugger protocol (`get_stack_dump` → `stack_dump`); `evaluate_expression` evaluates a GDScript expression at the given frame (`evaluate` → `evaluation_return`); `get_frame_variables` fetches locals, members, and globals (`get_stack_frame_vars` → `stack_frame_vars`). All three are captured via the poll-and-cache pattern on `MCPDebugger`, so the first call after a break may return empty data until the async reply arrives.

#### Profiling (issue #38) — category: `profiling` (gated off by default)

Read Godot's `Performance` monitors. Both `read_only`.

| Tool | Params | Returns |
|------|--------|---------|
| `get_editor_performance` | — | `EditorPerformanceResult { monitors }` |
| `get_performance_monitors` | `timeout_ms=2000` | `GamePerformanceResult { playing, connected, ready, monitors, hint }` |

`monitors` is a name→value map of a curated set: `fps`, `process_time`,
`physics_process_time`, `memory_static`/`_max`, `object_count`, `node_count`,
`resource_count`, `orphan_node_count`, `objects_drawn`, `primitives_drawn`, `draw_calls`,
`video_mem_used`, `texture_mem_used`, `buffer_mem_used`, `physics_2d_active`,
`physics_3d_active`. `get_editor_performance` reads the editor process directly;
`get_performance_monitors` reads the *running* game via the #66 runtime probe (a
`PRECONDITION_FAILED` with no play session, `connected=false` + hint without the probe). It
polls the probe up to `timeout_ms`; `ready` is true once a snapshot arrived (false on
timeout, with `monitors` empty). Render/memory metrics may read 0 under `--headless`.

#### Testing / QA (issue #37) — category: `testing` (gated off by default)

Automated play-testing, built entirely on the existing runtime/input/screenshot tools
(no new addon commands). Scenario/stress control the run (`runtime`); assertions and the
screenshot diff are `read_only`.

| Tool | Params | Returns |
|------|--------|---------|
| `assert_node_state` | `node_path, property, expected, op="==", timeout_ms=1500` | `AssertionResult { …, actual, passed, error }` |
| `run_test_scenario` | `scene="", events[], assertions[], setup_ms=800, settle_ms=300, stop_after=True` | `ScenarioResult { passed, played, connected, assertions[] }` |
| `run_stress_test` | `iterations=100, actions[], seed=0, delay_ms=8` | `StressTestResult { survived, iterations, playing_after, seed }` |
| `compare_screenshots` | `image_a, image_b (base64 PNG), tolerance=0.0` | `ScreenshotDiffResult { same_size, diff_pixels, diff_ratio, mean_abs_diff, match }` |

`assert_node_state` reads a live property (one sample via the runtime probe) and compares
with `op` (==, !=, <, <=, >, >=, contains, approx). `run_test_scenario` plays a scene,
runs an input sequence, then evaluates `{node_path, property, expected, op}` assertions
and stops the run. `run_stress_test` fuzzes the running game with seeded random input
(keys / input-map actions / "click") and reports whether it survived (still playing).
`compare_screenshots` does a per-pixel diff (via `pypng`) of two base64 PNGs — e.g. from
`capture_editor_screenshot` or saved baselines — with a per-channel `tolerance`.

#### Runtime inspection (issue #35) — `runtime` toolset, `read_only`

Inspect a *running* game on the #66 rails (the third piece, `get_game_scene_tree`, shipped
with #66). Requires a play session + the runtime probe.

| Tool | Params | Returns |
|------|--------|---------|
| `monitor_property` | `node_path, property, samples=30` | `MonitorResult { monitoring, node_path, property, samples }` |
| `get_property_samples` | — | `PropertySamplesResult { ready, connected, node_path, property, samples[], error }` |
| `find_ui_elements` | `name_contains="", class_filter="", visible_only=False, timeout_ms=2000` | `UiElementsResult { ready, elements[] }` |

`monitor_property` captures `samples` readings of a live node's property (one per frame —
`node_path` is an absolute path from `get_game_scene_tree`); collect the `[{frame, value}]`
series with `get_property_samples` (which reports a validation `error` for a bad
node/property). `find_ui_elements` returns matching Control nodes — each
`UiElement { path, name, node_class, visible, rect{x,y,w,h}, text }` —
and polls the probe up to `timeout_ms` for a fresh result. Each invocation carries an
internal `request_id` (constant across its poll), so the addon dispatches exactly one
full-Control scan per call and never returns a prior identical-filter request's stale
result. The `rect` pairs with `simulate_mouse` to click located UI.

### Diagnostics & debug workflow — `read_only` (category: `core`)

| Tool | Params | Returns | Notes |
|------|--------|---------|-------|
| `get_server_info` | — | `ServerDiagnostics { server, version, transport, toolsets[], prompts[], resources[], bridge{}, active_scene?, common_errors[], next_steps[] }` | capability snapshot — call first |
| `debug_workflow` | `scene="", timeout_seconds=5.0` | `DebugWorkflowResult { bridge{}, scene_tree?, run?, parse{ok, errors[], skipped_reason}, findings[], suggestions[] }` | one-call comprehensive check |

`get_server_info` returns the full server surface so an agent can discover everything in one call: toolset summaries with counts, registered prompt names, resource URIs, bridge state, active scene, common errors with fixes, and suggested next steps.

`debug_workflow` aggregates multiple read-only checks — parse errors across all `.gd` files, active scene tree, headless run capture, and bridge state — into a unified report with actionable findings and suggestions.

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

### Implemented prompts

| Prompt | Arguments | What it instructs |
|--------|-----------|-------------------|
| `toolset_discovery` | — | How to discover and enable gated toolsets at session start |
| `build_scene` | `scene_path`, `root_type` | Scaffold a new scene: enable toolsets, create/open scene, add nodes, attach scripts, add collision |
| `play_test` | `scene_path` | Live editor play-test: enable runtime, play scene, inspect tree, simulate input, assert state |
| `script_edit` | `script_path`, `node_path` | Write, attach, and verify a script: write_script → attach_script → get_parse_errors |
| `debug_scene` | `scene_path`, `script_path` | Systematic debugging: debug_workflow, get_parse_errors, run_and_capture, analyze_signal_flow, find_unused_resources, detect_circular_dependencies |
| `troubleshoot` | `error_message`, `scene_path`, `script_path` | Interpret a specific error message, find the source, and suggest fixes |

Prompts are discoverable via `list_prompts()` and renderable via `render_prompt(name, arguments={...})`.

## Client fallback

Provide a `resources-as-tools` / `prompts-as-tools` fallback for MCP clients that do not
implement the resource/prompt protocols, so the full surface is reachable as plain tools.
