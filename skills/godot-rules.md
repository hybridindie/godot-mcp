# Godot project rules (always on)

Load this file into your agent's always-on instructions (see `skills/README.md`).
It is the short version; the skills next to it hold the depth.

You are working in a Godot 4.x project with the Godot editor open on it, driven
through the Godot Editor MCP server. The project root is your working directory.

## Paths
- `res://` is the project root. `res://scripts/foo.gd` is the file `./scripts/foo.gd`.
- File tools (read, write, edit, search, shell) take filesystem paths: strip `res://`.
  Never pass a `res://` path to a file tool; it creates a folder literally named `res:`.
- MCP tools take `res://` paths and scene node paths (`.` is the scene root,
  `./Parent/Child` for children).

## Which tool for which change
- A tool category must be enabled before its tools exist:
  `godot_enable_toolset(category="scene_edit")`. `godot_list_toolsets()` lists them.
- Scripts (`.gd`): write or edit the file directly, then run
  `godot_scripts_get_parse_errors(script_path="res://…")` and fix every error before
  moving on.
- Scenes (`.tscn`) and nodes: use the MCP scene tools, such as
  `godot_scene_edit_create_node(…)`, `godot_scene_edit_set_node_property(…)` and
  `godot_scene_edit_attach_script(…)`. Never hand-edit a `.tscn` while the editor
  has it open; the editor overwrites the file when it saves.
- Save the scene with `godot_scene_edit_save_scene()` before you report done, unless
  the tool result already says `persisted: true`.

## Done means verified
- Read the result back before you report success: the file exists at the right
  path and parses, or the node shows up in `godot_inspection_get_scene_tree()` with
  the right type, parent, property values and script. If you can't verify it, say so.
- Do only what was asked. Don't add test files, refactors or extra nodes unless the
  request asks for them.

## GDScript 4.x
- First line `extends <Type>`; add `class_name` only when a global type is needed.
- Type every variable, parameter and return. Cast `load()`/`preload()`/`get_node()`:
  `var s := load("res://x.tscn") as PackedScene`.
- Godot 4 syntax only: `@export`, `@onready`, `signal.emit()`, `await`. No 3.x
  (`export var`, `yield`, string-based `connect`).
- Tabs for indentation, snake_case names. Don't name members after built-ins
  (`position`, `name`, `seed`).

## Tests (GUT), only when the request involves tests
- Tests extend `GutTest`, methods are named `test_*`, and setup goes in
  `before_each()` / `before_all()` (GUT calls no other setup method).
- Use real asserts only: `assert_eq`, `assert_ne`, `assert_true`, `assert_false`,
  `assert_almost_eq`, `assert_null`, `assert_not_null`, `assert_gt`, `assert_lt`,
  `assert_has`. Run them with `godot_testing_run_tests()`.

## Skills
- `godot-getting-started` — version check, toolset gating, the dry_run/confirm
  safety convention. Load it the first time you use the MCP tools in a session.
- `godot-expert` — engine rules and common bugs. Load it for anything beyond a
  single script or node: UI, physics, autoloads, shaders, animation. Its
  `references/` folder covers each area in depth.
- `godot-playtest-and-debug` — run the game, inspect it live, simulate input, debug.
