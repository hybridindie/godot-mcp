@tool
class_name MCPCommandRouter
extends RefCounted
## Routes incoming command envelopes to cmd_* handlers (issues #3, #5).
##
## Pure dispatch + structured errors; every outcome is a JSON-safe response
## envelope — { id, ok, result } or { id, ok:false, error, hint[, required] } —
## never a raw error or crash (see .opencode/rules/error-handling.md).
##
## Handlers receive the params dict and return a response *body* (without id) via
## the _ok / _fail builders; handle() stamps the id. Read-only inspection
## handlers (#5) read editor state through EditorInterface; safety/preconditions
## are owned by the MCP server, except the local guards needed to return a
## structured error instead of crashing.

const Inspect := preload("./scene_inspect.gd")
const Coerce := preload("./type_coerce.gd")

## The domain handler table (#522): adding a domain = one entry here, nothing
## else. Each script extends RefCounted, takes the router in _init, and exposes
## register(handlers) — the same contract every handler already satisfies.
## Order is irrelevant (registration is name-keyed); entries are alphabetical
## by file for readability.
const HANDLERS: Array = [
	preload("./handlers/animation.gd"),
	preload("./handlers/audio.gd"),
	preload("./handlers/batch.gd"),
	preload("./handlers/composite.gd"),
	preload("./handlers/debugger.gd"),
	preload("./handlers/editor.gd"),
	preload("./handlers/export.gd"),
	preload("./handlers/import_asset.gd"),
	preload("./handlers/input_map.gd"),
	preload("./handlers/input_recording.gd"),
	preload("./handlers/mesh_library.gd"),
	preload("./handlers/mutation.gd"),
	preload("./handlers/navigation.gd"),
	preload("./handlers/node_parity.gd"),
	preload("./handlers/particles.gd"),
	preload("./handlers/physics.gd"),
	preload("./handlers/profiling.gd"),
	preload("./handlers/project_fs.gd"),
	preload("./handlers/project_scaffold.gd"),
	preload("./handlers/resources.gd"),
	preload("./handlers/runtime_inspect.gd"),
	preload("./handlers/runtime_session.gd"),
	preload("./handlers/scene_3d.gd"),
	preload("./handlers/scene_inspect.gd"),
	preload("./handlers/scene_session.gd"),
	preload("./handlers/scripts.gd"),
	preload("./handlers/shaders.gd"),
	preload("./handlers/theme_ui.gd"),
	preload("./handlers/tilemap.gd"),
	preload("./handlers/tileset.gd"),
	preload("./handlers/visual_shader.gd"),
]

var _handlers: Dictionary = {}
## The RefCounted handler instances (one per HANDLERS entry) — promoted to a
## member so they survive beyond _init(); dispose() clears it.
var _instances: Array = []
## The server's package version, learned from cmd_server_hello (issue #521) and
## surfaced here so the plugin entry can label the dock "godot-mcp <ver> / Godot".
var server_version := ""
# The EditorDebuggerPlugin that captures a played game's godot_mcp channel (issue #66).
# Set by the plugin entry; null in headless/unit contexts where there is no editor.
var _debugger: Object = null
## The shared domain helpers (issue #522): handlers reach the shared logic
## through `_router._helpers` — no per-domain back-references, no cycle.
const MCPHelpers := preload("./mcp_helpers.gd")
var _helpers: MCPHelpers = null
## The consolidated runtime guards (#527).
const MCPGuards := preload("./mcp_guards.gd")
var _guards: MCPGuards = null


## Inject the MCPDebugger so runtime-inspection handlers can read cached live state.
func set_debugger(debugger: Object) -> void:
	_debugger = debugger


## Break the router/handler reference cycle so this cluster can actually be freed.
##
## Every handler keeps a `_router` back-reference, so neither side ever reaches a
## zero reference count; RefCounted cycles are never freed automatically (see the
## RefCounted class reference and weakref()). Called once from MCPBridge.dispose()
## on the plugin's exit path; commands arriving afterwards return the usual
## "Unknown command" error instead of dispatching.
func dispose() -> void:
	# #522: data-driven registration means there are no per-domain members to
	# clear — dropping the handler table + the helpers/guards references
	# frees the whole cluster (the handlers' only remaining back-reference
	# is via `_router` for the envelope builders, which dies with this object).
	_handlers.clear()
	_debugger = null
	_instances.clear()
	_helpers = null
	_guards = null

func _init() -> void:
	# Wire command strings are the cmd_<verb>_<noun> handler names (the matching MCP
	# tool drops the cmd_ prefix); see docs/architecture.md.
	_handlers["cmd_ping"] = _cmd_ping
	_handlers["cmd_get_project_info"] = _cmd_get_project_info
	# Server↔addon handshake (issue #530): addon version + Godot version + the
	# registered command list, consumed by the server's lazy handshake/cache and
	# surfaced in godot_get_server_info (fixes #521's never-assigned dock label).
	_handlers["cmd_get_addon_info"] = _cmd_get_addon_info
	# The server's half of the handshake (issue #521): it pushes its package
	# version right after fetching cmd_get_addon_info, so the dock can label the
	# connection "godot-mcp <calVer> / Godot <x.y.z>". Fire-and-forget from the
	# server (the response is ignored there); the addon stores + reflects it.
	_handlers["cmd_server_hello"] = _cmd_server_hello
	# Core: pop the current scene's undo history N steps (S4). Lives on the router
	# (not a domain handler) because it drives EditorUndoRedoManager directly.
	_handlers["cmd_undo"] = _cmd_undo
	# Core history parity + introspection (#529): redo mirrors undo; list_history
	# is the read-only orientation view of the same history. Same reason to live
	# on the router as cmd_undo — they drive EditorUndoRedoManager directly.
	_handlers["cmd_redo"] = _cmd_redo
	_handlers["cmd_list_history"] = _cmd_list_history
	# Meta-command: execute a batch of sub-commands in one frame (issue #167).
	# Lives on the router (not a domain handler) because it re-dispatches via _route.
	_handlers["cmd_run_commands"] = _cmd_run_commands
	_helpers = MCPHelpers.new()
	_guards = MCPGuards.new(self)
	_history_override = null
	# Data-driven registration (#522): every domain handler is one HANDLERS
	# table entry, instantiated and registered in this single loop. Instances go
	# into _instances (a member) so the RefCounted handlers survive beyond
	# _init(); dispose() clears it.
	for handler_script in HANDLERS:
		var handler: RefCounted = handler_script.new(self)
		handler.register(_handlers)
		_instances.append(handler)


## Dispatch one envelope ({ id, command, params }) and return a response envelope.
func handle(envelope: Dictionary) -> Dictionary:
	var body := _route(envelope)
	if not body.has("ok"):
		# A handler that died on a GDScript error returns nothing. Answer now instead of
		# sending an ok-less body the server can only drop and time out on (#466).
		body = _fail("INTERNAL_ERROR", "'%s' failed inside the addon without producing a response (a GDScript error — see the editor Output panel)." % str(envelope.get("command", "")))
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


## The UndoRedo object behind the edited scene's history — the one prologue the
## three history commands (cmd_undo / cmd_redo / cmd_list_history) share: the
## scene's object history when a scene is open, else the global history (null
## ur is handled by each caller, not here).
## A test-only seam overrides this (see _history_override).
var _history_override: UndoRedo = null


func _scene_history_undo_redo() -> UndoRedo:
	if _history_override != null:
		return _history_override
	var manager := EditorInterface.get_editor_undo_redo()
	var root := EditorInterface.get_edited_scene_root()
	var history_id: int = manager.get_object_history_id(root) if root != null else EditorUndoRedoManager.GLOBAL_HISTORY
	return manager.get_history_undo_redo(history_id)


## Test seam: pin the history commands to a specific UndoRedo object
## (godot/tests/history_smoke.gd, where the editor's manager is unavailable).
## Production never calls this; the plugin entry drops the seam on dispose.
func set_history_seam(ur: UndoRedo) -> void:
	_history_override = ur


## Undo the last `count` editor actions on the current scene's history (S4).
## Succeeds with `undone == 0` on an empty history (an empty-history undo is a
## no-op, not an error — the caller/reversibility ledger decides what that means).
func _cmd_undo(params: Dictionary) -> Dictionary:
	var count: int = int(params.get("count", 1))
	if count < 1:
		return _fail("VALIDATION_ERROR", "count must be >= 1")
	var dry_run: bool = bool(params.get("dry_run", false))
	var ur := _scene_history_undo_redo()
	if dry_run:
		# Preview only — the editor UndoRedo API can't report stack depth without
		# popping, so a dry-run reports whether an undo is available and the next
		# action's name, and performs nothing.
		var has_undo := ur != null and ur.has_undo()
		var next_action := ur.get_current_action_name() if has_undo else ""
		return _ok({"dry_run": true, "requested": count, "has_undo": has_undo, "would_undo_next": next_action})
	var undone := 0
	var last_action := ""
	while undone < count:
		if ur == null or not ur.has_undo():
			break
		last_action = ur.get_current_action_name()
		ur.undo()
		undone += 1
	return _ok({"undone": undone, "requested": count, "last_action": last_action, "dry_run": false})


## Redo the last `count` undone actions on the current scene's history (#529) —
## the mirror of _cmd_undo: same history targeting, same dry-run preview shape
## (has_redo + would_redo_next), same empty-history-is-a-no-op honesty.
func _cmd_redo(params: Dictionary) -> Dictionary:
	var count: int = int(params.get("count", 1))
	if count < 1:
		return _fail("VALIDATION_ERROR", "count must be >= 1")
	var dry_run: bool = bool(params.get("dry_run", false))
	var ur := _scene_history_undo_redo()
	if dry_run:
		var has_redo := ur != null and ur.has_redo()
		# The action redo() would re-apply sits one past the undo pointer; 4.7
		# has no dedicated getter, so resolve it via get_action_name(cur + 1)
		# (guaranteed in-bounds whenever has_redo). Empty = nothing to redo.
		var next_action := str(ur.get_action_name(ur.get_current_action() + 1)) if has_redo else ""
		return _ok({"dry_run": true, "requested": count, "has_redo": has_redo, "would_redo_next": next_action})
	var redone := 0
	var last_action := ""
	while redone < count:
		if ur == null or not ur.has_redo():
			break
		# Name the action about to be redone (mirrors the undo loop's
		# get_current_action_name() before popping).
		last_action = str(ur.get_action_name(ur.get_current_action() + 1))
		ur.redo()
		redone += 1
	return _ok({"redone": redone, "requested": count, "last_action": last_action, "dry_run": false})


## Read-only orientation view of the current scene's undo history (#529): the
## version counter (increments on every commit — a cheap change-detector),
## undo/redo availability, the current action name, and the recent action
## names via get_history_count + get_action_name (4.4+).
func _cmd_list_history(_params: Dictionary) -> Dictionary:
	var ur := _scene_history_undo_redo()
	var version := ur.get_version() if ur != null else 0
	var has_undo := ur != null and ur.has_undo()
	var has_redo := ur != null and ur.has_redo()
	var current := ur.get_current_action_name() if ur != null else ""
	var depth := ur.get_history_count() if ur != null else 0
	# Cap the orientation view: agents need the recent tail, not the whole stack.
	var recent: Array = []
	if ur != null:
		for i in range(depth):
			if recent.size() >= 20:
				break
			recent.append(str(ur.get_action_name(i)))
	return _ok({
		"version": version,
		"has_undo": has_undo,
		"has_redo": has_redo,
		# #529 ticket field (a literal-spec alias for has_redo, emitted so the
		# envelope matches the issue's documented field list).
		"can_redo": has_redo,
		"current_action": current,
		"depth": depth,
		"recent": recent,
	})


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
	# #461: honest partial completion — when stop_on_error halts the batch, the
	# response names the failing index and the skipped trailing count (e.g. a
	# trailing save_scene silently never ran). Reported regardless of the flag.
	var aborted_at := -1
	for entry in (raw as Array):
		if typeof(entry) != TYPE_DICTIONARY:
			# Every sub-result carries a "command" key so the server's SubCommandResult
			# (which requires it) validates even for a malformed entry.
			var bad := _fail("VALIDATION_ERROR", "Each command must be a {command, params} object.")
			bad["command"] = ""
			results.append(bad)
			ok_all = false
			aborted_at = results.size() - 1
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
			aborted_at = results.size() - 1
			if stop_on_error:
				break
	var body := {"results": results, "ok_all": ok_all, "count": results.size()}
	if stop_on_error and aborted_at >= 0:
		var skipped := (raw as Array).size() - (aborted_at + 1)
		body["aborted_at"] = aborted_at
		body["skipped_count"] = skipped
		body["hint"] = (
			"Batch stopped at command %d; %d later commands were not run — the scene may be unsaved. Re-run the remaining commands with stop_on_error=false or fix the failing command first."
			% [aborted_at, skipped]
		)
	return _ok(body)


func _cmd_get_project_info(_params: Dictionary) -> Dictionary:
	return _ok({
		"name": ProjectSettings.get_setting("application/config/name", ""),
		"godot_version": Engine.get_version_info().get("string", ""),
		"main_scene": ProjectSettings.get_setting("application/run/main_scene", ""),
		"project_path": ProjectSettings.globalize_path("res://"),
		"autoloads": _autoloads(),
		"input_actions": _input_actions(),
	})


## Self-description for the server↔addon handshake (issue #530, fixes #521):
## the addon's version (read live from plugin.cfg), the Godot version it runs
## inside, and the full set of registered cmd_* handler names. The server calls
## this lazily on its first exchange with the addon, caches the result, and
## surfaces it in godot_get_server_info — so a server↔addon version drift shows
## up as a visible mismatch in the capability snapshot instead of opaque
## per-command "Unknown command" errors.
func _cmd_get_addon_info(_params: Dictionary) -> Dictionary:
	var addon_version := ""
	var cfg := ConfigFile.new()
	if cfg.load("res://addons/godot_mcp/plugin.cfg") == OK:
		addon_version = str(cfg.get_value("plugin", "version", ""))
	return _ok({
		"addon_version": addon_version,
		"godot_version": Engine.get_version_info().get("string", ""),
		"commands": _handlers.keys(),
	})


## The server's half of the handshake (issue #521): store its package version
## so the plugin entry can label the dock "godot-mcp <ver> / Godot <x.y.z>".
## The server sends this fire-and-forget right after cmd_get_addon_info; the
## response envelope is ignored there (the addon needs no reply).
func _cmd_server_hello(params: Dictionary) -> Dictionary:
	server_version = str(params.get("version", ""))
	return _ok({"received": true})


# -- file system helpers (shared by scripts, shaders, resources) --------------

## Write text to a file (creating parent dirs) and tell the editor to re-import it.
## Used as the UndoRedo do/undo callback for script writes.
func _write_file_text(path: String, text: String) -> void:
	_helpers.write_file_text(path, text)


func _write_file_bytes(path: String, bytes: PackedByteArray) -> void:
	_helpers.write_file_bytes(path, bytes)


func _remove_file(path: String) -> void:
	_helpers.remove_file(path)


func _remove_file_with_uid(path: String) -> void:
	_helpers.remove_file_with_uid(path)


# -- property & node helpers (shared by many handlers) ------------------------

## Apply JSON properties to an object, coercing each value to the property's type.
## Unknown properties are skipped. Used for freshly-created (not-yet-in-tree) nodes,
## where the whole add is one undoable action.
func _apply_props(obj: Object, props: Dictionary) -> void:
	_helpers.apply_props(obj, props)


func _commit_add_child(parent: Node, child: Node, action_name: String) -> String:
	return _helpers.commit_add_child(parent, child, action_name)


func _commit_add_child_with_persistence(
	parent: Node, child: Node, action_name: String
) -> Dictionary:
	var persistence := _persistent_target(parent)
	var path := _commit_add_child(parent, child, action_name)
	return {"path": path, "persistence": persistence}


## Parse {ok, value: Vector2i} from a JSON [x, y] array or {x, y} dict, or a structured
## VALIDATION_ERROR keyed by `field`. Rejects missing/short/invalid input rather than
## silently defaulting components to 0 (which would target the wrong cell).
func _parse_vec2i(value: Variant, field: String) -> Dictionary:
	return _helpers.parse_vec2i(value, field, _parse_vec2i_ok, _fail)


## The ok-continuation parse_vec2i hands the parsed vector to (keeps the
## delegate one-line while the helpers module stays router-agnostic).
func _parse_vec2i_ok(value: Vector2i) -> Dictionary:
	return {"ok": true, "value": value}


func _valid_mouse_button(name: String) -> bool:
	return _helpers.valid_mouse_button(name)


func _invalid_input_event(event: Variant) -> String:
	return _helpers.invalid_input_event(event)


func _require_debug_session() -> Dictionary:
	return _guards.require_debug_session()


func _require_live_probe() -> Dictionary:
	return _guards.require_live_probe()


# -- instantiation helpers (shared by domain handlers) ------------------------

## Instantiate a class via ClassDB, validating it inherits from expected_base.
## Returns {ok: true, obj: Object} on success, or a VALIDATION_ERROR envelope;
## a type mismatch frees a non-RefCounted instance before failing (RefCounted
## resources are left to the caller / GC, as they can't be free()d directly).
## noun ("mesh", "shape", ...) is woven into the can-instantiate message.
## When expected_base is empty, only the can_instantiate + null checks run
## (useful for whitelist-validated types, or unions the caller checks itself).
func _instantiate_validated(cls_name: String, expected_base: String = "",
		noun: String = "") -> Dictionary:
	return _helpers.instantiate_validated(cls_name, _fail, expected_base, noun)


# -- resource helpers (shared by resources, theme_ui) ---------------------------

## Load a resource, set a property, and re-save — the UndoRedo callback for edits.
func _set_and_save_resource(path: String, property: String, value: Variant) -> void:
	_helpers.set_and_save_resource(path, property, value)


# -- scene-tree helpers (shared by mutations, node_parity) --------------------

## Set owner of a node and its whole subtree to the scene root so it is saved.
func _own_recursive(node: Node, root: Node) -> void:
	_helpers.own_recursive(node, root)


func _resolve(raw_path: Variant) -> Dictionary:
	return _helpers.resolve_node(raw_path, _fail)


# -- persistence truth (#458) -------------------------------------------------

## Whether a change to this node survives a scene save. Mirrors 4.7's
## SceneState::_parse_node: a node is packed only when its owner is the edited root or
## an editable instance, and a skipped node's subtree is never visited — so every node
## on the path up to the root must qualify. Returns {ok: true} or {ok: false, reason, hint}.
func _persistent_target(node: Node) -> Dictionary:
	return _helpers.persistent_target(node)


func _not_persisted(reason: String, hint: String) -> Dictionary:
	return _helpers._not_persisted(reason, hint)


func _with_persistence(result: Dictionary, verdict: Dictionary) -> Dictionary:
	return _helpers.with_persistence(result, verdict)


# -- UndoRedo batch-threshold decision (#523) ---------------------------------

## Whether a batch of `count` applies bypasses the undo stack (perf) — the one
## decision site for the shared threshold, so all three batch tools agree.
func _undoable_for_count(count: int) -> bool:
	return _helpers.undoable_for_count(count)


func _undo_threshold_hint(count: int, noun: String = "nodes") -> String:
	return _helpers.undo_threshold_hint(count, noun)


func _resource_persistence(node: Node, chain: Array) -> Dictionary:
	return _helpers.resource_persistence(node, chain)


func _group_removal_persistence(node: Node, group: String) -> Dictionary:
	return _helpers.group_removal_persistence(node, group)


func _base_states(node: Node) -> Array:
	return _helpers._base_states(node)


func _property_type(obj: Object, property: String) -> int:
	return _helpers.property_type(obj, property)


func _invalidate_prop_cache(obj: Object) -> void:
	_helpers.invalidate_prop_cache(obj)


func _valid_bits(value: Variant) -> bool:
	return _helpers.valid_bits(value)


func _bitmask(bits: Variant) -> int:
	return _helpers.bitmask(bits)


func _scene_name(root: Node) -> String:
	return _helpers.scene_name(root)


func _autoloads() -> Dictionary:
	return _helpers.autoloads()


func _input_actions() -> Array:
	return _helpers.input_actions()


# -- response builders --------------------------------------------------------

func _ok(result: Dictionary) -> Dictionary:
	return {"ok": true, "result": result}


func _fail(code: String, hint: String, required: String = "") -> Dictionary:
	var body: Dictionary = {"ok": false, "error": code, "hint": hint}
	if not required.is_empty():
		body["required"] = required
	return body
