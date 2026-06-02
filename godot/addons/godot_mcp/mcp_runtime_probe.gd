extends Node
## godot-mcp runtime probe (issue #66). Runs **in the game**, not the editor.
##
## Add this script as an autoload in the *consuming* game's project to enable godot-mcp
## live runtime inspection/input while the game runs from the editor. It registers an
## EngineDebugger message capture on the "godot_mcp" channel and answers queries from the
## addon's MCPDebugger (editor side). It does nothing outside a debug session, so it is
## safe to leave enabled (it no-ops in exported/non-debug builds).

const MAX_DEPTH := 32


func _ready() -> void:
	if EngineDebugger.is_active():
		EngineDebugger.register_message_capture("godot_mcp", _capture)
		EngineDebugger.send_message("godot_mcp:ready", [])


## Capture handler: the "godot_mcp:" prefix is stripped before this is called.
func _capture(message: String, _data: Array) -> bool:
	match message:
		"ping":
			EngineDebugger.send_message("godot_mcp:pong", [])
			return true
		"get_scene_tree":
			EngineDebugger.send_message("godot_mcp:scene_tree", [_serialize_tree()])
			return true
	return false


func _serialize_tree() -> Dictionary:
	return _node_to_dict(get_tree().root, 0)


## JSON-safe { name, type, path, children } snapshot of the live node, bounded by depth.
func _node_to_dict(node: Node, depth: int) -> Dictionary:
	var children: Array = []
	if depth < MAX_DEPTH:
		for child in node.get_children():
			children.append(_node_to_dict(child, depth + 1))
	return {
		"name": String(node.name),
		"type": node.get_class(),
		"path": String(node.get_path()),
		"children": children,
	}
