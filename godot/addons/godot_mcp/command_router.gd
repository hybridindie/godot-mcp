@tool
class_name MCPCommandRouter
extends RefCounted
## Routes incoming command envelopes to cmd_* handlers (issues #3, #5).
##
## Pure dispatch + structured errors; every outcome is a JSON-safe response
## envelope — { id, ok, result } or { id, ok:false, error, hint[, required] } —
## never a raw error or crash (see .claude/rules/error-handling.md).
##
## Handlers receive the params dict and return a response *body* (without id) via
## the _ok / _fail builders; handle() stamps the id. Read-only inspection
## handlers (#5) read editor state through EditorInterface; safety/preconditions
## are owned by the MCP server, except the local guards needed to return a
## structured error instead of crashing.

const Inspect := preload("res://addons/godot_mcp/scene_inspect.gd")
const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")
const MCPSceneInspectHandlers := preload("res://addons/godot_mcp/handlers/scene_inspect.gd")
const MCPMutationHandlers := preload("res://addons/godot_mcp/handlers/mutation.gd")
const MCPScriptHandlers := preload("res://addons/godot_mcp/handlers/scripts.gd")
const MCPNodeParityHandlers := preload("res://addons/godot_mcp/handlers/node_parity.gd")
const MCPAnimationHandlers := preload("res://addons/godot_mcp/handlers/animation.gd")
const MCPPhysicsHandlers := preload("res://addons/godot_mcp/handlers/physics.gd")
const MCPScene3DHandlers := preload("res://addons/godot_mcp/handlers/scene_3d.gd")
const MCPMeshLibraryHandlers := preload("res://addons/godot_mcp/handlers/mesh_library.gd")
const MCPParticlesHandlers := preload("res://addons/godot_mcp/handlers/particles.gd")
const MCPNavigationHandlers := preload("res://addons/godot_mcp/handlers/navigation.gd")
const MCPAudioHandlers := preload("res://addons/godot_mcp/handlers/audio.gd")
const MCPTileMapHandlers := preload("res://addons/godot_mcp/handlers/tilemap.gd")
const MCPTileSetHandlers := preload("res://addons/godot_mcp/handlers/tileset.gd")
const MCPThemeUIHandlers := preload("res://addons/godot_mcp/handlers/theme_ui.gd")
const MCPShadersHandlers := preload("res://addons/godot_mcp/handlers/shaders.gd")
const MCPRuntimeSessionHandlers := preload("res://addons/godot_mcp/handlers/runtime_session.gd")
const MCPRuntimeInspectHandlers := preload("res://addons/godot_mcp/handlers/runtime_inspect.gd")
const MCPInputRecordingHandlers := preload("res://addons/godot_mcp/handlers/input_recording.gd")
const MCPProfilingHandlers := preload("res://addons/godot_mcp/handlers/profiling.gd")
const MCPBatchHandlers := preload("res://addons/godot_mcp/handlers/batch.gd")
const MCPCompositeHandlers := preload("res://addons/godot_mcp/handlers/composite.gd")
const MCPExportHandlers := preload("res://addons/godot_mcp/handlers/export.gd")
const MCPEditorHandlers := preload("res://addons/godot_mcp/handlers/editor.gd")
const MCPProjectFSHandlers := preload("res://addons/godot_mcp/handlers/project_fs.gd")
const MCPResourcesHandlers := preload("res://addons/godot_mcp/handlers/resources.gd")
const MCPSceneSessionHandlers := preload("res://addons/godot_mcp/handlers/scene_session.gd")
const MCPInputMapHandlers := preload("res://addons/godot_mcp/handlers/input_map.gd")
const MCPDebuggerHandlers := preload("res://addons/godot_mcp/handlers/debugger.gd")
const MCPImportAssetHandlers := preload("res://addons/godot_mcp/handlers/import_asset.gd")
const MCPVisualShaderHandlers := preload("res://addons/godot_mcp/handlers/visual_shader.gd")
const MCPProjectScaffoldHandlers := preload("res://addons/godot_mcp/handlers/project_scaffold.gd")

var _handlers: Dictionary = {}
# The EditorDebuggerPlugin that captures a played game's godot_mcp channel (issue #66).
# Set by the plugin entry; null in headless/unit contexts where there is no editor.
var _debugger: Object = null
# Handler instances must NOT be local to _init() (they are RefCounted and get freed).
var _scene_inspect: MCPSceneInspectHandlers = null
var _mutation: MCPMutationHandlers = null
var _scripts: MCPScriptHandlers = null
var _node_parity: MCPNodeParityHandlers = null
var _animation: MCPAnimationHandlers = null
var _physics: MCPPhysicsHandlers = null
var _scene_3d: MCPScene3DHandlers = null
var _mesh_library: MCPMeshLibraryHandlers = null
var _particles: MCPParticlesHandlers = null
var _navigation: MCPNavigationHandlers = null
var _audio: MCPAudioHandlers = null
var _tilemap: MCPTileMapHandlers = null
var _tileset: MCPTileSetHandlers = null
var _theme_ui: MCPThemeUIHandlers = null
var _shaders: MCPShadersHandlers = null
var _runtime_session: MCPRuntimeSessionHandlers = null
var _runtime_inspect: MCPRuntimeInspectHandlers = null
var _input_recording: MCPInputRecordingHandlers = null
var _profiling: MCPProfilingHandlers = null
var _batch: MCPBatchHandlers = null
var _composite: MCPCompositeHandlers = null
var _export: MCPExportHandlers = null
var _editor: MCPEditorHandlers = null
var _project_fs: MCPProjectFSHandlers = null
var _resources: MCPResourcesHandlers = null
var _scene_session: MCPSceneSessionHandlers = null
var _input_map: MCPInputMapHandlers = null
var _debugger_handlers: MCPDebuggerHandlers = null
var _import_asset: MCPImportAssetHandlers = null
var _visual_shader: MCPVisualShaderHandlers = null
var _project_scaffold: MCPProjectScaffoldHandlers = null


## Inject the MCPDebugger so runtime-inspection handlers can read cached live state.
func set_debugger(debugger: Object) -> void:
	_debugger = debugger


func _init() -> void:
	# Wire command strings are the cmd_<verb>_<noun> handler names (the matching MCP
	# tool drops the cmd_ prefix); see docs/architecture.md.
	_handlers["cmd_ping"] = _cmd_ping
	_handlers["cmd_get_project_info"] = _cmd_get_project_info
	# Meta-command: execute a batch of sub-commands in one frame (issue #167).
	# Lives on the router (not a domain handler) because it re-dispatches via _route.
	_handlers["cmd_run_commands"] = _cmd_run_commands
	# Instances are promoted to member variables so RefCounted objects survive
	# beyond _init(); see discussion in git history.
	_scene_inspect = MCPSceneInspectHandlers.new(self)
	_scene_inspect.register(_handlers)
	_mutation = MCPMutationHandlers.new(self)
	_mutation.register(_handlers)
	_scripts = MCPScriptHandlers.new(self)
	_scripts.register(_handlers)
	_node_parity = MCPNodeParityHandlers.new(self)
	_node_parity.register(_handlers)
	_animation = MCPAnimationHandlers.new(self)
	_animation.register(_handlers)
	_physics = MCPPhysicsHandlers.new(self)
	_physics.register(_handlers)
	_scene_3d = MCPScene3DHandlers.new(self)
	_scene_3d.register(_handlers)
	_mesh_library = MCPMeshLibraryHandlers.new(self)
	_mesh_library.register(_handlers)
	_particles = MCPParticlesHandlers.new(self)
	_particles.register(_handlers)
	_navigation = MCPNavigationHandlers.new(self)
	_navigation.register(_handlers)
	_audio = MCPAudioHandlers.new(self)
	_audio.register(_handlers)
	_tilemap = MCPTileMapHandlers.new(self)
	_tilemap.register(_handlers)
	_tileset = MCPTileSetHandlers.new(self)
	_tileset.register(_handlers)
	_theme_ui = MCPThemeUIHandlers.new(self)
	_theme_ui.register(_handlers)
	_shaders = MCPShadersHandlers.new(self)
	_shaders.register(_handlers)
	_runtime_session = MCPRuntimeSessionHandlers.new(self)
	_runtime_session.register(_handlers)
	_runtime_inspect = MCPRuntimeInspectHandlers.new(self)
	_runtime_inspect.register(_handlers)
	_input_recording = MCPInputRecordingHandlers.new(self)
	_input_recording.register(_handlers)
	_profiling = MCPProfilingHandlers.new(self)
	_profiling.register(_handlers)
	_batch = MCPBatchHandlers.new(self)
	_batch.register(_handlers)
	_composite = MCPCompositeHandlers.new(self)
	_composite.register(_handlers)
	_export = MCPExportHandlers.new(self)
	_export.register(_handlers)
	_editor = MCPEditorHandlers.new(self)
	_editor.register(_handlers)
	_project_fs = MCPProjectFSHandlers.new(self)
	_project_fs.register(_handlers)
	_resources = MCPResourcesHandlers.new(self)
	_resources.register(_handlers)
	_scene_session = MCPSceneSessionHandlers.new(self)
	_scene_session.register(_handlers)
	_input_map = MCPInputMapHandlers.new(self)
	_input_map.register(_handlers)
	_debugger_handlers = MCPDebuggerHandlers.new(self)
	_debugger_handlers.register(_handlers)
	_import_asset = MCPImportAssetHandlers.new(self)
	_import_asset.register(_handlers)
	_visual_shader = MCPVisualShaderHandlers.new(self)
	_visual_shader.register(_handlers)
	_project_scaffold = MCPProjectScaffoldHandlers.new(self)
	_project_scaffold.register(_handlers)


## Dispatch one envelope ({ id, command, params }) and return a response envelope.
func handle(envelope: Dictionary) -> Dictionary:
	var body := _route(envelope)
	body["id"] = str(envelope.get("id", ""))
	return body


func has_command(command: String) -> bool:
	return _handlers.has(command)


func _route(envelope: Dictionary) -> Dictionary:
	if not envelope.has("command"):
		return _fail("VALIDATION_ERROR", "Envelope is missing 'command'.")
	var command := str(envelope["command"])
	if not _handlers.has(command):
		return _fail("VALIDATION_ERROR", "Unknown command '%s'." % command)
	var raw_params: Variant = envelope.get("params", {})
	if typeof(raw_params) != TYPE_DICTIONARY:
		return _fail("VALIDATION_ERROR", "'params' must be an object.")
	var handler: Callable = _handlers[command]
	return handler.call(raw_params as Dictionary)


func _cmd_ping(_params: Dictionary) -> Dictionary:
	return _ok({"pong": true})


## Execute a batch of sub-commands in a single frame and return one response body
## per command (issue #167). The editor drains commands serially (~one frame each),
## so collapsing N round-trips into one is the main throughput lever for scripted
## harnesses. Each sub-command re-enters _route, so its own handler still registers
## UndoRedo. With stop_on_error (default true) the batch halts at the first failure.
## The outer envelope is always ok:true (the batch ran); inspect per-command "ok".
func _cmd_run_commands(params: Dictionary) -> Dictionary:
	var raw: Variant = params.get("commands", [])
	if typeof(raw) != TYPE_ARRAY:
		return _fail("VALIDATION_ERROR", "'commands' must be an array of {command, params}.")
	var stop_on_error := bool(params.get("stop_on_error", true))
	var results: Array = []
	var ok_all := true
	for entry in (raw as Array):
		if typeof(entry) != TYPE_DICTIONARY:
			# Every sub-result carries a "command" key so the server's SubCommandResult
			# (which requires it) validates even for a malformed entry.
			var bad := _fail("VALIDATION_ERROR", "Each command must be a {command, params} object.")
			bad["command"] = ""
			results.append(bad)
			ok_all = false
			if stop_on_error:
				break
			continue
		var entry_dict := entry as Dictionary
		var sub_command := str(entry_dict.get("command", ""))
		# Refuse to nest run_commands in itself: re-dispatching it would recurse
		# _cmd_run_commands -> _route -> _cmd_run_commands and crash the editor.
		var sub: Dictionary
		if sub_command == "cmd_run_commands" or sub_command == "run_commands":
			sub = _fail("VALIDATION_ERROR", "run_commands cannot be nested inside run_commands.")
		else:
			sub = _route(entry_dict)
		sub["command"] = sub_command
		results.append(sub)
		if not bool(sub.get("ok", false)):
			ok_all = false
			if stop_on_error:
				break
	return _ok({"results": results, "ok_all": ok_all, "count": results.size()})


func _cmd_get_project_info(_params: Dictionary) -> Dictionary:
	return _ok({
		"name": ProjectSettings.get_setting("application/config/name", ""),
		"godot_version": Engine.get_version_info().get("string", ""),
		"main_scene": ProjectSettings.get_setting("application/run/main_scene", ""),
		"project_path": ProjectSettings.globalize_path("res://"),
		"autoloads": _autoloads(),
		"input_actions": _input_actions(),
	})


# -- file system helpers (shared by scripts, shaders, resources) --------------

## Write text to a file (creating parent dirs) and tell the editor to re-import it.
## Used as the UndoRedo do/undo callback for script writes.
func _write_file_text(path: String, text: String) -> void:
	var base_dir := path.get_base_dir()
	if not DirAccess.dir_exists_absolute(base_dir):
		DirAccess.make_dir_recursive_absolute(base_dir)
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file != null:
		file.store_string(text)
		file.close()
	EditorInterface.get_resource_filesystem().update_file(path)


## Write raw bytes to a file (creating parent dirs) and re-import it. The UndoRedo
## undo callback for file deletion (#217), so binary resources round-trip exactly.
func _write_file_bytes(path: String, bytes: PackedByteArray) -> void:
	var base_dir := path.get_base_dir()
	if not DirAccess.dir_exists_absolute(base_dir):
		DirAccess.make_dir_recursive_absolute(base_dir)
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file != null:
		file.store_buffer(bytes)
		file.close()
	EditorInterface.get_resource_filesystem().update_file(path)


func _remove_file(path: String) -> void:
	if FileAccess.file_exists(path):
		DirAccess.remove_absolute(path)
		EditorInterface.get_resource_filesystem().update_file(path)


## Remove a file and its Godot 4.4+ ".uid" sidecar (if present), so undoing a
## freshly-created resource leaves nothing orphaned.
func _remove_file_with_uid(path: String) -> void:
	_remove_file(path)
	var uid_path := path + ".uid"
	if FileAccess.file_exists(uid_path):
		DirAccess.remove_absolute(uid_path)
		EditorInterface.get_resource_filesystem().update_file(uid_path)


# -- property & node helpers (shared by many handlers) ------------------------

## Apply JSON properties to an object, coercing each value to the property's type.
## Unknown properties are skipped. Used for freshly-created (not-yet-in-tree) nodes,
## where the whole add is one undoable action.
func _apply_props(obj: Object, props: Dictionary) -> void:
	for key in props:
		var pt := _property_type(obj, str(key))
		if pt != -1:
			obj.set(str(key), Coerce.from_json(props[key], pt))


## Add `child` under `parent` as one undoable action; return its scene-relative path.
func _commit_add_child(parent: Node, child: Node, action_name: String) -> String:
	var root := EditorInterface.get_edited_scene_root()
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action(action_name)
	ur.add_do_method(parent, "add_child", child)
	ur.add_do_method(child, "set_owner", root)
	ur.add_do_reference(child)
	ur.add_undo_method(parent, "remove_child", child)
	ur.commit_action()
	return Inspect.relative_path(child, root)


## Parse {ok, value: Vector2i} from a JSON [x, y] array or {x, y} dict, or a structured
## VALIDATION_ERROR keyed by `field`. Rejects missing/short/invalid input rather than
## silently defaulting components to 0 (which would target the wrong cell).
func _parse_vec2i(value: Variant, field: String) -> Dictionary:
	if value is Array and (value as Array).size() == 2:
		return {"ok": true, "value": Vector2i(int(value[0]), int(value[1]))}
	if value is Dictionary and value.has("x") and value.has("y"):
		return {"ok": true, "value": Vector2i(int(value["x"]), int(value["y"]))}
	return _fail("VALIDATION_ERROR", "'%s' must be [x, y] integer coordinates." % field)


const _SIM_MOUSE_BUTTONS := ["left", "right", "middle", "wheel_up", "wheel_down"]


## A mouse button name is valid when empty (motion) or a known button.
func _valid_mouse_button(name: String) -> bool:
	return name.is_empty() or name in _SIM_MOUSE_BUTTONS


## Return a reason string if an input-sequence event is malformed, else "" (valid).
func _invalid_input_event(event: Variant) -> String:
	if not (event is Dictionary):
		return "must be an object"
	match str(event.get("type", "")):
		"key":
			return "" if not str(event.get("key", "")).is_empty() else "'key' is required"
		"action":
			return "" if not str(event.get("action", "")).is_empty() else "'action' is required"
		"mouse":
			return "" if _valid_mouse_button(str(event.get("button", ""))) else "invalid 'button'"
		_:
			return "'type' must be key/mouse/action"


## Guard for input injection: a play session must be live with its probe connected.
## Guard for breakpoint operations: a play session must be live with a valid debug session.
func _require_debug_session() -> Dictionary:
	if not EditorInterface.is_playing_scene():
		return _fail("PRECONDITION_FAILED", "No play session. Run play_scene first.", "play_session")
	if _debugger == null:
		return _fail("INTERNAL_ERROR", "Debugger plugin is unavailable.")
	if _debugger.get_session_id() < 0:
		return _fail("PRECONDITION_FAILED", "No active debug session. The game may not have connected to the editor debugger yet.", "play_session")
	return {"ok": true}


func _require_live_probe() -> Dictionary:
	if not EditorInterface.is_playing_scene():
		return _fail("PRECONDITION_FAILED", "No play session. Run play_scene first.", "play_session")
	if _debugger == null or not _debugger.is_connected_to_probe():
		return _fail("PRECONDITION_FAILED", "The godot_mcp runtime probe is not connected; add it as an autoload in the game.", "runtime_probe")
	return {"ok": true}


# -- batch / refactor helpers (shared) ----------------------------------------

# -- export helpers (shared) --------------------------------------------------

# -- editor screenshot helpers ------------------------------------------------

# -- project & filesystem helpers (shared) ------------------------------------

# -- resource helpers (shared by resources, theme_ui) ---------------------------

## Load a resource, set a property, and re-save — the UndoRedo callback for edits.
func _set_and_save_resource(path: String, property: String, value: Variant) -> void:
	var res: Resource = ResourceLoader.load(path)
	if res == null:
		return
	res.set(property, value)
	ResourceSaver.save(res, path)
	EditorInterface.get_resource_filesystem().update_file(path)


# -- scene-tree helpers (shared by mutations, node_parity) --------------------

## Set owner of a node and its whole subtree to the scene root so it is saved.
func _own_recursive(node: Node, root: Node) -> void:
	if node != root:
		node.owner = root
	for child in node.get_children():
		_own_recursive(child, root)


## Resolve a node by scene-relative path, returning {ok, node} or an error body.
func _resolve(raw_path: Variant) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var path_str := Inspect.normalize_node_path(str(raw_path))
	var node: Node = root.get_node_or_null(NodePath(path_str))
	if node == null:
		return _fail("RESOURCE_NOT_FOUND", "No node at '%s'." % str(raw_path))
	return {"ok": true, "node": node}


## The Variant.Type of an object's property, or -1 if it has no such property.
## Uses a per-object cache so repeated lookups (e.g. batch operations) are O(1)
## instead of O(n) over the property list. Cache refreshes automatically on a
## cache miss so attaching scripts / adding exported vars doesn't leave stale data.
var _prop_cache: Dictionary = {}  # {Object instance_id: {name: type}}
const MAX_PROP_CACHE_SIZE := 256

func _prune_prop_cache() -> void:
	if _prop_cache.size() > MAX_PROP_CACHE_SIZE:
		_prop_cache.clear()

func _property_type(obj: Object, property: String) -> int:
	var obj_id := obj.get_instance_id()
	var cache: Dictionary = _prop_cache.get(obj_id, {})
	if not cache.has(property):
		# Refresh cache on miss: property list may have changed (script attached, etc.)
		cache = {}
		for entry in obj.get_property_list():
			cache[entry["name"]] = int(entry["type"])
		_prop_cache[obj_id] = cache
		_prune_prop_cache()
	return cache.get(property, -1)


## Call after a batch operation that mutated many objects so stale caches don't leak.
func _invalidate_prop_cache(obj: Object) -> void:
	_prop_cache.erase(obj.get_instance_id())


func _scene_name(root: Node) -> String:
	if not root.scene_file_path.is_empty():
		return root.scene_file_path.get_file()
	return String(root.name)


func _autoloads() -> Dictionary:
	var autoloads: Dictionary = {}
	for entry in ProjectSettings.get_property_list():
		var key: String = entry["name"]
		if key.begins_with("autoload/"):
			autoloads[key.trim_prefix("autoload/")] = str(ProjectSettings.get_setting(key, ""))
	return autoloads


func _input_actions() -> Array:
	var actions: Array = []
	for entry in ProjectSettings.get_property_list():
		var key: String = entry["name"]
		if key.begins_with("input/"):
			actions.append(key.trim_prefix("input/"))
	return actions


# -- response builders --------------------------------------------------------

func _ok(result: Dictionary) -> Dictionary:
	return {"ok": true, "result": result}


func _fail(code: String, hint: String, required: String = "") -> Dictionary:
	var body: Dictionary = {"ok": false, "error": code, "hint": hint}
	if not required.is_empty():
		body["required"] = required
	return body
