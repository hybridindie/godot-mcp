@tool
class_name MCPHelpers
extends RefCounted
## The shared domain helpers the handlers consume (issue #522).
##
## The command router used to host all of this, which made it a helpers
## grab-bag rather than pure dispatch: file I/O, node resolution, the
## property-type cache, persistence truth (#458/#477), instantiation
## validation, the #523 batch-threshold decision, input validation, and
## project-info collectors. Handlers now reach for THIS module (via the
## router's `_helpers` reference, which carries no back-reference cycle into
## the handlers), and the router stays dispatch + envelope builders +
## router-owned commands.
##
## Everything returning to the bridge stays JSON-safe (see
## .opencode/rules/addon.md); Godot type coercion lives in type_coerce.gd and
## is never duplicated here.

const Inspect := preload("./scene_inspect.gd")
const Coerce := preload("./type_coerce.gd")

## The shared UndoRedo 20-node threshold (issue #523, extends #461): batches of
## property applies / node creates / node edits above this size bypass
## EditorUndoRedoManager for perf and MUST report `undoable: false` + a hint —
## the agent otherwise believes undo covers the whole batch. One const owns the
## value so a future retune updates the hint too (it interpolates this).
const UNDO_THRESHOLD := 20


# -- file system helpers (shared by scripts, shaders, resources) --------------

## Write text to a file (creating parent dirs) and tell the editor to re-import it.
## Used as the UndoRedo do/undo callback for script writes.
func write_file_text(path: String, text: String) -> void:
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
func write_file_bytes(path: String, bytes: PackedByteArray) -> void:
	var base_dir := path.get_base_dir()
	if not DirAccess.dir_exists_absolute(base_dir):
		DirAccess.make_dir_recursive_absolute(base_dir)
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file != null:
		file.store_buffer(bytes)
		file.close()
	EditorInterface.get_resource_filesystem().update_file(path)


func remove_file(path: String) -> void:
	if FileAccess.file_exists(path):
		DirAccess.remove_absolute(path)
		EditorInterface.get_resource_filesystem().update_file(path)


## Remove a file and its Godot 4.4+ ".uid" sidecar (if present), so undoing a
## freshly-created resource leaves nothing orphaned.
func remove_file_with_uid(path: String) -> void:
	remove_file(path)
	var uid_path := path + ".uid"
	if FileAccess.file_exists(uid_path):
		DirAccess.remove_absolute(uid_path)
		EditorInterface.get_resource_filesystem().update_file(uid_path)


# -- property & node helpers (shared by many handlers) ------------------------

## Apply JSON properties to an object, coercing each value to the property's type.
## Unknown properties are skipped. Used for freshly-created (not-yet-in-tree) nodes,
## where the whole add is one undoable action.
func apply_props(obj: Object, props: Dictionary) -> void:
	for key in props:
		var pt := property_type(obj, str(key))
		if pt != -1:
			obj.set(str(key), Coerce.from_json(props[key], pt))


## Add `child` under `parent` as one undoable action; return its scene-relative path.
func commit_add_child(parent: Node, child: Node, action_name: String) -> String:
	var root := EditorInterface.get_edited_scene_root()
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action(action_name)
	ur.add_do_method(parent, "add_child", child)
	ur.add_do_method(child, "set_owner", root)
	ur.add_do_reference(child)
	ur.add_undo_method(parent, "remove_child", child)
	ur.commit_action()
	return Inspect.relative_path(child, root)


## #477: the same commit as :meth:`commit_add_child`, plus the persistence verdict
## for the create (the parent rule — probed BEFORE the child is added). Returns
## {path, persistence} so create-family handlers stamp their results uniformly.
func commit_add_child_with_persistence(
	parent: Node, child: Node, action_name: String
) -> Dictionary:
	var persistence := persistent_target(parent)
	var path := commit_add_child(parent, child, action_name)
	return {"path": path, "persistence": persistence}


## Parse {ok, value: Vector2i} from a JSON [x, y] array or {x, y} dict, or a structured
## VALIDATION_ERROR keyed by `field`. Rejects missing/short/invalid input rather than
## silently defaulting components to 0 (which would target the wrong cell).
func parse_vec2i(value: Variant, field: String, ok: Callable, fail: Callable) -> Dictionary:
	if value is Array and (value as Array).size() == 2:
		return ok.call(Vector2i(int(value[0]), int(value[1])))
	if value is Dictionary and value.has("x") and value.has("y"):
		return ok.call(Vector2i(int(value["x"]), int(value["y"])))
	return fail.call("VALIDATION_ERROR", "'%s' must be [x, y] integer coordinates." % field)


# -- instantiation helpers (shared by domain handlers) ------------------------

## Instantiate a class via ClassDB, validating it inherits from expected_base.
## Returns {ok: true, obj: Object} on success, or a VALIDATION_ERROR envelope;
## a type mismatch frees a non-RefCounted instance before failing (RefCounted
## resources are left to the caller / GC, as they can't be free()d directly).
## noun ("mesh", "shape", ...) is woven into the can-instantiate message.
## When expected_base is empty, only the can_instantiate + null checks run
## (useful for whitelist-validated types, or unions the caller checks itself).
## `fail` is the caller's envelope builder so error codes stay centralized.
func instantiate_validated(
	cls_name: String, fail: Callable, expected_base: String = "", noun: String = ""
) -> Dictionary:
	var label := "'%s'" % cls_name if noun.is_empty() else "%s '%s'" % [noun, cls_name]
	if not ClassDB.can_instantiate(cls_name):
		return fail.call("VALIDATION_ERROR", "Cannot instantiate %s." % label)
	var obj: Object = ClassDB.instantiate(cls_name)
	if obj == null:
		return fail.call("VALIDATION_ERROR", "Could not instantiate '%s'." % cls_name)
	if not expected_base.is_empty() and cls_name != expected_base and not ClassDB.is_parent_class(cls_name, expected_base):
		if not (obj is RefCounted):
			obj.free()
		return fail.call("VALIDATION_ERROR", "'%s' is not a %s." % [cls_name, expected_base])
	return {"ok": true, "obj": obj}


# -- resource helpers (shared by resources, theme_ui) ---------------------------

## Load a resource, set a property, and re-save — the UndoRedo callback for edits.
func set_and_save_resource(path: String, property: String, value: Variant) -> void:
	var res: Resource = ResourceLoader.load(path)
	if res == null:
		return
	res.set(property, value)
	ResourceSaver.save(res, path)
	EditorInterface.get_resource_filesystem().update_file(path)


# -- scene-tree helpers (shared by mutations, node_parity) --------------------

## Set owner of a node and its whole subtree to the scene root so it is saved.
func own_recursive(node: Node, root: Node) -> void:
	if node != root:
		node.owner = root
	for child in node.get_children():
		own_recursive(child, root)


## Resolve a node by scene-relative path, returning {ok, node} or an error body.
## `fail` is the caller's envelope builder (the router's _fail) so error codes
## stay centralized there.
func resolve_node(raw_path: Variant, fail: Callable) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return fail.call("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var path_str := Inspect.normalize_node_path(str(raw_path))
	var node: Node = root.get_node_or_null(NodePath(path_str))
	if node == null:
		return fail.call("RESOURCE_NOT_FOUND", "No node at '%s'." % str(raw_path))
	return {"ok": true, "node": node}


# -- persistence truth (#458) -------------------------------------------------

## Whether a change to this node survives a scene save. Mirrors 4.7's
## SceneState::_parse_node: a node is packed only when its owner is the edited root or
## an editable instance, and a skipped node's subtree is never visited — so every node
## on the path up to the root must qualify. Returns {ok: true} or {ok: false, reason, hint}.
func persistent_target(node: Node) -> Dictionary:
	# A null node is never persisted regardless of scene state — checked before
	# the editor access so the guard holds even where the editor is absent
	# (headless tests; the editor hard-errors on get_edited_scene_root there).
	if node == null:
		return _not_persisted("node_not_owned", "No scene is open, so nothing can be saved.")
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _not_persisted("node_not_owned", "No scene is open, so nothing can be saved.")
	var current := node
	while current != root:
		if current == null:
			return _not_persisted("node_not_owned", "The target is not inside the edited scene, so changes to it are never saved.")
		var node_owner := current.owner
		if node_owner == null:
			return _not_persisted(
				"node_not_owned",
				"'%s' has no owner in the edited scene (e.g. it was added by a @tool script), so it is not saved — the change shows in the editor but is lost on reload." % root.get_path_to(current)
			)
		if node_owner != root and not root.is_editable_instance(node_owner):
			var instance := str(root.get_path_to(node_owner))
			return _not_persisted(
				"instanced_child_not_editable",
				"'%s' is inside the instanced scene '%s', which does not have Editable Children enabled — the change shows in the editor but will not be saved. Enable Editable Children on '%s', or target a node the scene owns." % [root.get_path_to(node), instance, instance]
			)
		current = current.get_parent()
	return {"ok": true}


func _not_persisted(reason: String, hint: String) -> Dictionary:
	return {"ok": false, "reason": reason, "hint": hint}


## Stamp a persistence verdict onto a mutation result: always `persisted`, plus `reason`
## and `hint` when the applied change will not be saved.
func with_persistence(result: Dictionary, verdict: Dictionary) -> Dictionary:
	var persisted := bool(verdict.get("ok", false))
	result["persisted"] = persisted
	if not persisted:
		result["reason"] = str(verdict.get("reason", ""))
		result["hint"] = str(verdict.get("hint", ""))
	return result


# -- UndoRedo batch-threshold decision (#523) ---------------------------------

## Whether a batch of `count` applies bypasses the undo stack (perf) — the one
## decision site for the shared threshold, so all three batch tools agree.
func undoable_for_count(count: int) -> bool:
	return count <= UNDO_THRESHOLD


## The #461/#523 hint for a non-undoable batch: names the size and the shared
## threshold so a future retune updates one place. Single-sourced — every
## threshold-aware tool stamps this into its result verbatim.
func undo_threshold_hint(count: int, noun: String = "nodes") -> String:
	return (
		"%d %s exceeds the %d-node UndoRedo threshold: this batch was applied "
		+ "directly without undo support. Undo will not revert it."
	) % [count, noun, UNDO_THRESHOLD]


## Whether an edit to a resource the node uses survives a scene save. `chain` is the edited
## resource first, then each resource embedding it, out to the one the node holds; the first
## with a path decides. A sub-resource of the edited scene saves with the node. A resource
## file, or a sub-resource of a loaded non-scene file, is saved by the editor alongside the
## scene (EditorNode::_save_external_resources, 4.7) even when the node is not. A sub-resource
## of another scene is never re-saved. No path at all: embedded through the node itself.
func resource_persistence(node: Node, chain: Array) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	for item in chain:
		var resource := item as Resource
		if resource == null or resource.resource_path.is_empty():
			continue
		var container := resource.resource_path.get_slice("::", 0)
		if root != null and container == root.scene_file_path:
			break
		if not resource.resource_path.contains("::"):
			return {"ok": true}
		if ResourceLoader.has_cached(container) and not (ResourceLoader.get_cached_ref(container) is PackedScene):
			return {"ok": true}
		return _not_persisted(
			"embedded_in_other_resource",
			"This %s is embedded in '%s', which is not saved with the current scene — the change shows in the editor but is lost on reload. Edit it in '%s' directly, or give the node its own %s." % [resource.get_class(), container, container, resource.get_class()]
		)
	return persistent_target(node)


## Whether removing `group` from this node survives a save. The packer writes only the groups
## a node adds on top of the scenes it comes from (SceneState::_parse_node, 4.7), so a group an
## instanced or inherited scene gives the node is back after a reload.
func group_removal_persistence(node: Node, group: String) -> Dictionary:
	var verdict := persistent_target(node)
	if not verdict["ok"]:
		return verdict
	for entry in _base_states(node):
		var state: SceneState = entry[0]
		if group in state.get_node_groups(entry[1]):
			var source := state.get_path() if not state.get_path().is_empty() else "the scene it comes from"
			return _not_persisted(
				"group_from_base_scene",
				"'%s' gets group '%s' from '%s', so removing it is not saved — the group is back after a reload. Remove it in '%s' instead." % [EditorInterface.get_edited_scene_root().get_path_to(node), group, source, source]
			)
	return verdict


## The saved scene states this node comes from, as [SceneState, node index] pairs — the
## GDScript mirror of 4.7's PropertyUtils::get_node_states_stack, which the packer diffs a
## node against. Empty for a node only the edited scene defines. Node's own state accessors
## are not exposed to scripts, so each level's state is read from its (cached) PackedScene.
func _base_states(node: Node) -> Array:
	var root := EditorInterface.get_edited_scene_root()
	var states := []
	var current := node
	while current != null:
		var state: SceneState = null
		if current == root:
			if not root.scene_file_path.is_empty() and ResourceLoader.exists(root.scene_file_path):
				var own := load(root.scene_file_path) as PackedScene
				if own != null:
					state = own.get_state().get_base_scene_state()
		elif not current.scene_file_path.is_empty():
			var instanced := load(current.scene_file_path) as PackedScene
			if instanced != null:
				state = instanced.get_state()
		var relative := current.get_path_to(node)
		while state != null:
			for i in state.get_node_count():
				if str(state.get_node_path(i)).trim_prefix("./") == str(relative):  # SceneState paths read "./Label"
					states.append([state, i])
					break
			state = state.get_base_scene_state()
		if current == root:
			break
		current = current.owner
	return states


# -- property-type cache (batch-heavy paths) ----------------------------------

## The Variant.Type of an object's property, or -1 if it has no such property.
## Uses a per-object cache so repeated lookups (e.g. batch operations) are O(1)
## instead of O(n) over the property list. Cache refreshes automatically on a
## cache miss so attaching scripts / adding exported vars doesn't leave stale data.
var _prop_cache: Dictionary = {}  # {Object instance_id: {name: type}}
const MAX_PROP_CACHE_SIZE := 256

func _prune_prop_cache() -> void:
	if _prop_cache.size() > MAX_PROP_CACHE_SIZE:
		_prop_cache.clear()

func property_type(obj: Object, property: String) -> int:
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
func invalidate_prop_cache(obj: Object) -> void:
	_prop_cache.erase(obj.get_instance_id())


# -- input validation (shared by runtime_session) ------------------------------

const SIM_MOUSE_BUTTONS := ["left", "right", "middle", "wheel_up", "wheel_down"]


## A mouse button name is valid when empty (motion) or a known button.
func valid_mouse_button(name: String) -> bool:
	return name.is_empty() or name in SIM_MOUSE_BUTTONS


## Return a reason string if an input-sequence event is malformed, else "" (valid).
func invalid_input_event(event: Variant) -> String:
	if not (event is Dictionary):
		return "must be an object"
	match str(event.get("type", "")):
		"key":
			return "" if not str(event.get("key", "")).is_empty() else "'key' is required"
		"action":
			return "" if not str(event.get("action", "")).is_empty() else "'action' is required"
		"mouse":
			return "" if valid_mouse_button(str(event.get("button", ""))) else "invalid 'button'"
		_:
			return "'type' must be key/mouse/action"


# -- bitmask math (shared by physics, navigation) ------------------------------

## Shared by handlers that take 1-based bit indices (physics layers/mask,
## navigation layers). A valid value is an array of ints in [1, 32].
func valid_bits(value: Variant) -> bool:
	if not (value is Array):
		return false
	for bit in value:
		if typeof(bit) not in [TYPE_INT, TYPE_FLOAT]:
			return false
		var index := int(bit)
		if index < 1 or index > 32:
			return false
	return true


## Fold an array of 1-based bit indices into a bitmask. Out-of-range bits are
## ignored; validate with valid_bits first to reject bad input.
func bitmask(bits: Variant) -> int:
	var mask := 0
	if bits is Array:
		for bit in bits:
			var index := int(bit)
			if index >= 1 and index <= 32:
				mask |= 1 << (index - 1)
	return mask


func scene_name(root: Node) -> String:
	if not root.scene_file_path.is_empty():
		return root.scene_file_path.get_file()
	return String(root.name)


func autoloads() -> Dictionary:
	var autoloads: Dictionary = {}
	for entry in ProjectSettings.get_property_list():
		var key: String = entry["name"]
		if key.begins_with("autoload/"):
			autoloads[key.trim_prefix("autoload/")] = str(ProjectSettings.get_setting(key, ""))
	return autoloads


func input_actions() -> Array:
	var actions: Array = []
	for entry in ProjectSettings.get_property_list():
		var key: String = entry["name"]
		if key.begins_with("input/"):
			actions.append(key.trim_prefix("input/"))
	return actions