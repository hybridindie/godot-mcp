@tool
class_name MCPAnimationHandlers
extends RefCounted
## Domain handler: animation.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

const Inspect := preload("res://addons/godot_mcp/scene_inspect.gd")

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_add_animation_track"] = _cmd_add_animation_track
	handlers["cmd_add_state_machine_state"] = _cmd_add_state_machine_state
	handlers["cmd_create_animation"] = _cmd_create_animation
	handlers["cmd_create_animation_tree"] = _cmd_create_animation_tree
	handlers["cmd_insert_keyframe"] = _cmd_insert_keyframe
	handlers["cmd_set_blend_tree_node"] = _cmd_set_blend_tree_node


# -- handlers ----------------------------------------------------------------

const _TRACK_TYPES := {
	"value": Animation.TYPE_VALUE,
	"position_3d": Animation.TYPE_POSITION_3D,
	"rotation_3d": Animation.TYPE_ROTATION_3D,
	"scale_3d": Animation.TYPE_SCALE_3D,
	"method": Animation.TYPE_METHOD,
	"bezier": Animation.TYPE_BEZIER,
	"audio": Animation.TYPE_AUDIO,
	"animation": Animation.TYPE_ANIMATION,
}
func _cmd_create_animation(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var player: Node = found["node"]
	if not (player is AnimationPlayer):
		return _router._fail("VALIDATION_ERROR", "Node is not an AnimationPlayer.")
	var anim_name := str(params.get("name", ""))
	if anim_name.is_empty():
		return _router._fail("VALIDATION_ERROR", "'name' must be a non-empty string.")

	var created_lib := false
	var library: AnimationLibrary
	if player.has_animation_library(""):
		library = player.get_animation_library("")
	else:
		library = AnimationLibrary.new()
		created_lib = true
	if library.has_animation(anim_name):
		return _router._fail("VALIDATION_ERROR", "Animation '%s' already exists." % anim_name)

	var animation := Animation.new()
	animation.length = float(params.get("length", 1.0))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Create animation %s" % anim_name)
	if created_lib:
		ur.add_do_method(player, "add_animation_library", "", library)
		ur.add_do_reference(library)
	ur.add_do_method(library, "add_animation", anim_name, animation)
	ur.add_do_reference(animation)
	ur.add_undo_method(library, "remove_animation", anim_name)
	if created_lib:
		ur.add_undo_method(player, "remove_animation_library", "")
	ur.commit_action()
	return _router._ok({"player_path": str(params.get("node_path")), "animation": anim_name, "length": animation.length})



func _cmd_add_animation_track(params: Dictionary) -> Dictionary:
	var found := _resolve_player_animation(params)
	if not found["ok"]:
		return found
	var animation: Animation = found["animation"]
	var track_type_key := str(params.get("track_type", "value"))
	if not _TRACK_TYPES.has(track_type_key):
		return _router._fail("VALIDATION_ERROR", "Unknown track_type '%s'." % track_type_key)
	var track_type: int = _TRACK_TYPES[track_type_key]
	var track_path := str(params.get("track_path", ""))
	if track_path.is_empty():
		return _router._fail("VALIDATION_ERROR", "'track_path' must be a non-empty string.")
	var index := animation.get_track_count()  # add_track appends to this index
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add animation track")
	ur.add_do_method(animation, "add_track", track_type, -1)
	ur.add_do_method(animation, "track_set_path", index, NodePath(track_path))
	ur.add_undo_method(animation, "remove_track", index)
	ur.commit_action()
	return _router._ok({"animation": str(params.get("animation")), "track": index, "track_path": track_path})



func _cmd_insert_keyframe(params: Dictionary) -> Dictionary:
	var found := _resolve_player_animation(params)
	if not found["ok"]:
		return found
	var animation: Animation = found["animation"]
	var track := int(params.get("track", -1))
	if track < 0 or track >= animation.get_track_count():
		return _router._fail("VALIDATION_ERROR", "Track %d is out of range." % track)
	var time := float(params.get("time", 0.0))
	var easing := float(params.get("easing", 1.0))
	var value: Variant = params.get("value")
	if value is String:  # accept string forms like "Vector2(10, 20)" (issue #51)
		var parsed: Variant = str_to_var(value)
		if parsed != null:
			value = parsed
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Insert keyframe")
	ur.add_do_method(animation, "track_insert_key", track, time, value, easing)
	ur.add_undo_method(animation, "track_remove_key_at_time", track, time)
	ur.commit_action()
	return _router._ok({"animation": str(params.get("animation")), "track": track, "time": time})



func _cmd_create_animation_tree(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var root := EditorInterface.get_edited_scene_root()
	var root_type := str(params.get("root_type", "AnimationNodeStateMachine"))
	if not ClassDB.can_instantiate(root_type):
		return _router._fail("VALIDATION_ERROR", "Cannot instantiate '%s'." % root_type)
	var tree_root_obj: Object = ClassDB.instantiate(root_type)
	if not (tree_root_obj is AnimationRootNode):
		if not (tree_root_obj is RefCounted):
			tree_root_obj.free()
		return _router._fail("VALIDATION_ERROR", "'%s' is not an AnimationRootNode." % root_type)

	var tree := AnimationTree.new()
	tree.name = str(params.get("name", "AnimationTree"))
	tree.tree_root = tree_root_obj
	if params.get("anim_player") != null:
		tree.anim_player = NodePath(str(params["anim_player"]))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Create AnimationTree %s" % tree.name)
	ur.add_do_method(parent, "add_child", tree)
	ur.add_do_method(tree, "set_owner", root)
	ur.add_do_reference(tree)
	ur.add_undo_method(parent, "remove_child", tree)
	ur.commit_action()
	return _router._ok({"node_path": Inspect.relative_path(tree, root), "root_type": root_type})



func _cmd_add_state_machine_state(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("tree_path", ""))
	if not found["ok"]:
		return found
	var tree: Node = found["node"]
	if not (tree is AnimationTree) or not (tree.tree_root is AnimationNodeStateMachine):
		return _router._fail("VALIDATION_ERROR", "Node is not an AnimationTree with a state-machine root.")
	var state_machine: AnimationNodeStateMachine = tree.tree_root
	var state_name := str(params.get("state_name", ""))
	if state_name.is_empty():
		return _router._fail("VALIDATION_ERROR", "'state_name' must be a non-empty string.")
	var state := AnimationNodeAnimation.new()
	if params.get("animation") != null:
		state.animation = StringName(str(params["animation"]))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add state %s" % state_name)
	ur.add_do_method(state_machine, "add_node", state_name, state, Vector2.ZERO)
	ur.add_do_reference(state)
	ur.add_undo_method(state_machine, "remove_node", state_name)
	ur.commit_action()
	return _router._ok({"tree_path": str(params.get("tree_path")), "state": state_name})



func _cmd_set_blend_tree_node(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("tree_path", ""))
	if not found["ok"]:
		return found
	var tree: Node = found["node"]
	if not (tree is AnimationTree) or not (tree.tree_root is AnimationNodeBlendTree):
		return _router._fail("VALIDATION_ERROR", "Node is not an AnimationTree with a blend-tree root.")
	var blend_tree: AnimationNodeBlendTree = tree.tree_root
	var node_name := str(params.get("node_name", ""))
	if node_name.is_empty():
		return _router._fail("VALIDATION_ERROR", "'node_name' must be a non-empty string.")
	var node_type := str(params.get("node_type", ""))
	if not ClassDB.can_instantiate(node_type):
		return _router._fail("VALIDATION_ERROR", "Cannot instantiate '%s'." % node_type)
	var anim_node_obj: Object = ClassDB.instantiate(node_type)
	if not (anim_node_obj is AnimationNode):
		if not (anim_node_obj is RefCounted):
			anim_node_obj.free()
		return _router._fail("VALIDATION_ERROR", "'%s' is not an AnimationNode." % node_type)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add blend-tree node %s" % node_name)
	ur.add_do_method(blend_tree, "add_node", node_name, anim_node_obj, Vector2.ZERO)
	ur.add_do_reference(anim_node_obj)
	ur.add_undo_method(blend_tree, "remove_node", node_name)
	ur.commit_action()
	return _router._ok({"tree_path": str(params.get("tree_path")), "node": node_name, "node_type": node_type})


func _resolve_player_animation(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var player: Node = found["node"]
	if not (player is AnimationPlayer):
		return _router._fail("VALIDATION_ERROR", "Node is not an AnimationPlayer.")
	var anim_name := str(params.get("animation", ""))
	if not player.has_animation(anim_name):
		return _router._fail("RESOURCE_NOT_FOUND", "No animation '%s' on the AnimationPlayer." % anim_name)
	return {"ok": true, "animation": player.get_animation(anim_name)}


