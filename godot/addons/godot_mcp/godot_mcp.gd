@tool
extends EditorPlugin
## godot-mcp EditorPlugin entry point.
##
## This is the ONLY layer that touches the Godot Editor API. It currently
## establishes live editor presence: a read-only status dock that reflects
## connection state, project path, active scene, selected node, and a recent
## command log (issue #2). The WebSocket bridge and cmd_* command router land in
## issue #3 — that introduces TCPServer/WebSocketPeer (verify against the Godot
## 4.4 docs before use, per .claude/rules/addon.md).
##
## API note: add_control_to_dock()/remove_control_from_docks() are deprecated as
## of Godot 4.6 in favour of EditorDock/add_dock(), but EditorDock does not exist
## in 4.4/4.5 and this project targets 4.4+, so the broadly-compatible API is the
## correct choice here.

const PLUGIN_NAME := "godot_mcp"
const MCPDockScript := preload("res://addons/godot_mcp/mcp_dock.gd")

var _dock: VBoxContainer
var _selection: EditorSelection


func _enter_tree() -> void:
	_dock = MCPDockScript.new()
	add_control_to_dock(DOCK_SLOT_LEFT_UR, _dock)

	# No bridge yet (issue #3); presence is "disconnected" for now.
	_dock.set_connection_status(MCPDockScript.ConnectionStatus.DISCONNECTED)

	# Live editor state: refresh on selection and scene changes.
	_selection = EditorInterface.get_selection()
	_selection.selection_changed.connect(_on_selection_changed)
	scene_changed.connect(_on_scene_changed)

	_refresh_all()


func _exit_tree() -> void:
	if _selection != null and _selection.selection_changed.is_connected(_on_selection_changed):
		_selection.selection_changed.disconnect(_on_selection_changed)
	if scene_changed.is_connected(_on_scene_changed):
		scene_changed.disconnect(_on_scene_changed)
	_selection = null

	if _dock != null:
		remove_control_from_docks(_dock)
		_dock.queue_free()
		_dock = null


func _get_plugin_name() -> String:
	return PLUGIN_NAME


## Push the full current editor state into the dock (used on enable).
func _refresh_all() -> void:
	_dock.set_project_path(ProjectSettings.globalize_path("res://"))
	_on_scene_changed(EditorInterface.get_edited_scene_root())
	_on_selection_changed()


func _on_scene_changed(scene_root: Node) -> void:
	_dock.set_active_scene(_scene_label(scene_root))


func _on_selection_changed() -> void:
	var nodes := _selection.get_selected_nodes()
	_dock.set_selected_node(nodes[0].name if not nodes.is_empty() else "")


## Human-readable name for the active scene: its file name, else the root node
## name, else empty (the dock renders empty as a placeholder).
func _scene_label(scene_root: Node) -> String:
	if scene_root == null:
		return ""
	if not scene_root.scene_file_path.is_empty():
		return scene_root.scene_file_path.get_file()
	return scene_root.name
