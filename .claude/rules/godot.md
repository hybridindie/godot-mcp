---
read_when: "Writing or changing GDScript, scenes, autoloads, or Godot project settings"
paths:
  - "godot/**/*.gd"
  - "godot/**/*.tscn"
  - "godot/project.godot"
---

# Godot Project Conventions

Applies to games and editor tools alike; `addon.md` adds the rules for
`EditorPlugin` code.

## MUST

- Static typing in GDScript: typed variables, parameters, and return values.
- Scenes own their children; reach outward with signals, not with
  `get_parent()` chains or absolute node paths into other scenes.
- Autoloads hold cross-scene services only, never per-scene state.
- Never block the main thread (see `godot-async.md`).
- Deterministic logic that tests depend on (procedural generation,
  simulation) takes its seed, time, and inputs as parameters.
- Commit `.uid` and `.import` metadata alongside the assets they describe;
  never hand-edit them.

## SHOULD

- Pure logic in plain `RefCounted` classes that can be tested without a scene.
- `class_name` for reusable types; one public type per file.
- `@export` for designer-tuned values instead of literals in code.
- Performance-critical or native code (GDExtension, Rust) sits behind a narrow
  GDScript API.

## ANTI-PATTERNS

- `print()` as the error channel; use `push_error` / `push_warning` plus an
  explicit return value.
- Polling in `_process` for something a signal could announce.
- String-typed node lookups scattered across scripts.
