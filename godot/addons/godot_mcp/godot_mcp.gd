@tool
extends EditorPlugin
## godot-mcp EditorPlugin entry point.
##
## This is the ONLY layer that touches the Godot Editor API. It owns the
## read-only status dock (issue #2) and the WebSocket bridge (issue #3): a
## localhost WebSocket server that routes command envelopes to cmd_* handlers and
## reflects connection state + recent commands in the dock. All safety/preconditions
## live in the MCP server, not here.
##
## API note: add_control_to_dock()/remove_control_from_docks() are deprecated as
## of Godot 4.6 in favour of EditorDock/add_dock(), but EditorDock does not exist
## in 4.4/4.5 and this project targets 4.4+, so the broadly-compatible API is the
## correct choice here.

const PLUGIN_NAME := "godot_mcp"
# Minimum supported Godot version. The addon is built for 4.4+ (UID sidecars, the
# 4.4-compatible add_control_to_dock choice) and is validated against 4.6.x.
const MIN_GODOT_MAJOR := 4
const MIN_GODOT_MINOR := 4

var _dock: MCPStatusDock
var _bridge: MCPBridge
var _debugger: MCPDebugger
var _selection: EditorSelection


func _enter_tree() -> void:
	_warn_if_unsupported_version()
	_dock = MCPStatusDock.new()
	add_control_to_dock(DOCK_SLOT_LEFT_UR, _dock)

	# Capture the godot_mcp debugger channel from played games (issue #66), and give the
	# router a handle so runtime-inspection handlers can read the cached live state.
	_debugger = MCPDebugger.new()
	add_debugger_plugin(_debugger)
	var router := MCPCommandRouter.new()
	router.set_debugger(_debugger)

	# Start the WebSocket bridge and reflect its state in the dock.
	_bridge = MCPBridge.new(router)
	_bridge.connection_changed.connect(_on_connection_changed)
	_bridge.command_received.connect(_dock.log_command)
	add_child(_bridge)
	# Connect out to the MCP server's bridge listener (#276). The URL is overridable via
	# GODOT_MCP_BRIDGE_URL (no hard-coded endpoint per .claude/rules/architecture.md);
	# defaults to ws://127.0.0.1:9080.
	var bridge_url := OS.get_environment("GODOT_MCP_BRIDGE_URL")
	if bridge_url.is_empty():
		bridge_url = MCPBridge.DEFAULT_URL
	_bridge.start(bridge_url)

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

	if _bridge != null:
		_bridge.stop()
		_bridge.queue_free()
		_bridge = null

	if _debugger != null:
		remove_debugger_plugin(_debugger)
		_debugger = null

	if _dock != null:
		remove_control_from_docks(_dock)
		_dock.queue_free()
		_dock = null


func _get_plugin_name() -> String:
	return PLUGIN_NAME


## Warn (don't hard-refuse) when the editor is older than the supported floor, so a user on
## an unsupported version gets a clear message instead of cryptic parse/runtime errors.
func _warn_if_unsupported_version() -> void:
	var info := Engine.get_version_info()
	var major := int(info.get("major", 0))
	var minor := int(info.get("minor", 0))
	if major < MIN_GODOT_MAJOR or (major == MIN_GODOT_MAJOR and minor < MIN_GODOT_MINOR):
		push_warning(
			"godot_mcp supports Godot %d.%d+ (running %s). Some features may misbehave on this version."
			% [MIN_GODOT_MAJOR, MIN_GODOT_MINOR, str(info.get("string", "unknown"))]
		)


## Push the full current editor state into the dock (used on enable).
func _refresh_all() -> void:
	_dock.set_project_path(ProjectSettings.globalize_path("res://"))
	_on_scene_changed(EditorInterface.get_edited_scene_root())
	_on_selection_changed()


func _on_connection_changed(status: MCPBridge.Status) -> void:
	# MCPBridge.Status and MCPStatusDock.ConnectionStatus share ordering by design.
	_dock.set_connection_status(status as MCPStatusDock.ConnectionStatus)


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
