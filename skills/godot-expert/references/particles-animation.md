# Particles, Animation & Navigation Authoring

Three runtime-heavy content domains. Each has one "make the thing" tool then
"tune the thing" tools. This is the `particles`, `animation`, and `navigation`
toolsets.

---

## Particles

GPU particles are a node plus a `ParticleProcessMaterial`. The toolset builds
both.

| Tool | Purpose |
|------|---------|
| `godot_particles_create(parent_path, particles_type="GPUParticles2D", amount, lifetime, properties)` | node + a fresh process material |
| `godot_particles_apply_preset(node_path, preset)` | one of `fire`/`smoke`/`explosion`/`sparks` — a tuned starting point |
| `godot_particles_set_material(node_path, properties)` | tune `gravity`, `initial_velocity_min`/`max`, `scale_min`/`max`, `spread`, `color` |
| `godot_particles_set_color_gradient(node_path, colors, offsets)` | the color-over-lifetime ramp |
| `godot_particles_get_material(node_path)` | read it back (properties + gradient) |

### Pitfalls

- **`amount` is total particles in flight, not spawn rate.** `lifetime`
  (seconds) divided into `amount` is the effective spawn rate; both are set at
  create time and both shape the look.
- **A preset is a starting point, not a lock.** `apply_preset` sets node +
  material + gradient; follow with `set_material`/`set_color_gradient` to tune.
- **`emitting` must be true** — a created emitter defaults to emitting, but a
  tuned-down `one_shot` fires once and stops. Check `emitting`/`one_shot` when
  "nothing appears."
- **`GPUParticles3D` needs a draw pass mesh.** A 3D emitter with no
  `draw_pass` renders nothing even though it simulates. For quick VFX, a
  `QuadMesh`/`BoxMesh` draw pass is the usual fix.
- **The gradient is built and assigned for you** — `set_color_gradient` makes a
  `GradientTexture1D`; pass `offsets` 0..1 (evenly spaced if omitted).

---

## Animation

An `AnimationPlayer` holds named `Animation` resources; each has tracks
(property/position/rotation/method/bezier/audio/animation), each track has
keyframes.

| Tool | Purpose |
|------|---------|
| `godot_animation_create(node_path, name, length)` | new empty `Animation` on the player |
| `godot_animation_add_track(node_path, animation, track_path, track_type)` | add a track; returns its **index** |
| `godot_animation_insert_keyframe(node_path, animation, track, time, value, easing)` | key it |
| `godot_animation_list_animations(node_path)` / `godot_animation_get(node_path, animation_name)` | read back |

### Pitfalls

- **`track_path` is `"NodeName:property"`** (e.g. `"Sprite2D:position"`,
  `"Player:velocity"`), relative to the AnimationPlayer's root. A wrong path
  creates a track that animates nothing.
- **`track` is the numeric index** returned by `add_track` — not the path.
  Insert keyframes by index; reordering tracks shifts indices.
- **`track_type` must match the property**: `value` (generic),
  `position_3d`/`rotation_3d`/`scale_3d` (3D transforms), `method`, `bezier`,
  `audio`, `animation`. A `position` animated as `value` won't interpolate.
- **`value` accepts Godot-string forms** (`"Vector2(10, 20)"`), coerced by the
  addon — the same contract as `set_node_property`.
- **Keyframe `time` is seconds**, within `length`; keys past `length` are
  clamped/ignored.

### AnimationTree

For state machines: `create_animation_tree(parent_path, name, anim_player,
root_type)` (default root `AnimationNodeStateMachine`), then
`add_state_machine_state(tree_path, state_name, animation)` and
`set_blend_tree_node(tree_path, node_name, node_type)`. Attach a state
machine to the player's animations by state `animation` name.

---

## Navigation

A region bakes a navmesh from the geometry around it; an agent paths over it.

```
setup_navigation_region → bake_navigation_mesh → setup_navigation_agent
   (the walkable area)      (compute the mesh)    (the pathfinder)
```

| Tool | Purpose |
|------|---------|
| `godot_navigation_setup_region(parent_path, region_type="NavigationRegion2D")` | region with an empty navmesh |
| `godot_navigation_bake_mesh(node_path)` | bake the navmesh from surrounding collision/geometry |
| `godot_navigation_setup_agent(parent_path, agent_type="NavigationAgent2D")` | the pathfinder node |
| `godot_navigation_set_layers(node_path, layers)` | nav-layer bitmask |
| `godot_navigation_get_region(node_path)` | read the baked polygon/mesh |

### Pitfalls

- **Bake after the geometry exists.** `bake_navigation_mesh` samples the
  collision/geometry present at bake time; bake too early and the navmesh is
  empty or misses walls. Re-bake after moving obstacles.
- **Navigation needs collision geometry to sample.** A region over decorative
  sprites with no `CollisionShape2D`/`StaticBody2D` bakes nothing walkable.
- **Agent and region must share nav layers.** An agent set to layer 1 won't
  path on a region on layer 2 — `set_navigation_layers` both, or leave both at
  the default.
- **`region_type` / `agent_type` name the 2D or 3D class explicitly** —
  `NavigationRegion2D`/`NavigationAgent2D` vs the `3D` forms; they don't infer.

---

## Common thread

All three are **runtime content**: author, then verify by reading back
(`get_material`, `get_animation`, `get_region`) or by play-testing. Each
supports `dry_run` — preview the shape before committing a burst of edits.
