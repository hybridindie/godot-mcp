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
## API note: add_control_to_bottom_panel() is deprecated as of Godot 4.6 in
## favour of EditorDock/add_dock() with DOCK_SLOT_BOTTOM, but EditorDock does
## not exist in 4.4/4.5 and this project targets 4.4+, so the broadly-
## compatible API is the correct choice here. The bottom panel is the natural
## home for a status/log display (alongside Output and Debug), not a tab
## competing with Scene/Import in the dock area.

const PLUGIN_NAME := "godot_mcp"
const MIN_GODOT_MAJOR := 4
const MIN_GODOT_MINOR := 4
const REFRESH_INTERVAL := 2.0  # seconds between connection-status polls

# #539: the cached status-icon textures (one per connection status, built
# lazily by the helper this module consumes).
const StatusIcons := preload("./mcp_status_icons.gd")

var _dock: MCPStatusDock
var _dock_button: Button
var _bridge: MCPBridge
var _debugger: MCPDebugger
var _router: MCPCommandRouter
var _selection: EditorSelection
var _refresh_timer: Timer
var _server_version := ""
# #539: the lazily-built, cached status-icon textures (a RefCounted helper, so
# the textures live exactly as long as the plugin).
var _status_icons: StatusIcons


func _enter_tree() -> void:
	_warn_if_unsupported_version()
	_status_icons = StatusIcons.new()
	_dock = MCPStatusDock.new()
	_dock_button = add_control_to_bottom_panel(_dock, "MCP")
	# Auto-show the bottom panel and set the initial status icon.
	if _dock_button != null:
		_dock_button.button_pressed = true
		_update_button_icon(MCPBridge.Status.DISCONNECTED)

	# Feed static info the dock can show immediately.
	_dock.set_server_version(_server_version_label())
	_dock.set_bridge_url(_bridge_url())

	_debugger = MCPDebugger.new()
	add_debugger_plugin(_debugger)
	var router := MCPCommandRouter.new()
	router.set_debugger(_debugger)
	_router = router  # kept for the cmd_server_hello version label (#521)

	# Start the WebSocket bridge and reflect its state in the dock.
	_bridge = MCPBridge.new(router)
	_bridge.connection_changed.connect(_on_connection_changed)
	_bridge.command_received.connect(_dock.log_command)
	_bridge.command_completed.connect(_on_command_completed)
	add_child(_bridge)
	_bridge.start(_bridge_url())

	# Live editor state: refresh on selection and scene changes.
	_selection = EditorInterface.get_selection()
	_selection.selection_changed.connect(_on_selection_changed)
	scene_changed.connect(_on_scene_changed)

	# Auto-refresh: poll connection status periodically so a dropped
	# connection is visible without an editor action.
	_refresh_timer = Timer.new()
	_refresh_timer.wait_time = REFRESH_INTERVAL
	_refresh_timer.autostart = true
	_refresh_timer.timeout.connect(_on_refresh_timer)
	add_child(_refresh_timer)

	_refresh_all()


func _exit_tree() -> void:
	if _refresh_timer != null:
		_refresh_timer.stop()
		_refresh_timer.queue_free()
		_refresh_timer = null

	if _selection != null and _selection.selection_changed.is_connected(_on_selection_changed):
		_selection.selection_changed.disconnect(_on_selection_changed)
	if scene_changed.is_connected(_on_scene_changed):
		scene_changed.disconnect(_on_scene_changed)
	_selection = null

	if _bridge != null:
		# dispose() drops the router/handler references before the node goes away.
		_bridge.dispose()
		# Drop the router's test-only history seam with the plugin's dispose path.
		_router.set_history_seam(null)
		_bridge.queue_free()
		_bridge = null
	_router = null

	if _debugger != null:
		# dispose() drops the plugin's own references before it is unregistered.
		_debugger.dispose()
		remove_debugger_plugin(_debugger)
		_debugger = null

	if _dock != null:
		remove_control_from_bottom_panel(_dock)
		_dock.queue_free()
		_dock = null
		_dock_button = null
	_status_icons = null


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
	_dock.set_bridge_url(_bridge_url())
	_dock.set_server_version(_server_version_label())
	_on_scene_changed(EditorInterface.get_edited_scene_root())
	_on_selection_changed()


func _on_connection_changed(status: MCPBridge.Status) -> void:
	# MCPBridge.Status and MCPStatusDock.ConnectionStatus share ordering by design.
	_dock.set_connection_status(status as MCPStatusDock.ConnectionStatus)
	_update_button_icon(status)


func _on_scene_changed(scene_root: Node) -> void:
	_dock.set_active_scene(_scene_label(scene_root))


func _on_selection_changed() -> void:
	var nodes := _selection.get_selected_nodes()
	_dock.set_selected_node(nodes[0].name if not nodes.is_empty() else "")


func _on_refresh_timer() -> void:
	# Sync the dock's connection status with the bridge's actual state.
	# The bridge emits connection_changed on transitions, but if the server
	# process dies the bridge may not fire the signal — this poll catches that.
	if _bridge != null:
		var status := _bridge.get_status()
		_dock.set_connection_status(status as MCPStatusDock.ConnectionStatus)
		_update_button_icon(status)
	# Issue #521: the server pushes its version via cmd_server_hello after the
	# handshake; the router stores it in server_version. Reflect it on the next
	# tick so the dock label goes from "Godot x.y.z" to
	# "godot-mcp <calver> / Godot x.y.z" without a dedicated signal path.
	if _router != null and _router.server_version != _server_version:
		_server_version = _router.server_version
		_dock.set_server_version(_server_version_label())


## Set the bottom-bar button icon to a colored dot reflecting connection status.
## In Godot 4.7, add_control_to_bottom_panel returns a legacy dummy Button
## that isn't rendered — the real tab is managed by EditorDock. So we also
## update the dock's internal status dot (which is always visible when the
## panel is open). The button icon is set as a best-effort for 4.4/4.5 where
## the button is the real tab toggle.
func _update_button_icon(status: MCPBridge.Status) -> void:
	# Best-effort: set the legacy button icon (works on 4.4/4.5, no-op on 4.7).
	if _dock_button != null:
		# #539: three statuses → three immutable textures, built once (lazily)
		# and cached for the plugin's lifetime — the hot path only swaps a
		# reference (no per-status-change 256-pixel regeneration).
		_dock_button.icon = _status_icons.texture(status as int)


## Human-readable name for the active scene: its file name, else the root node
## name, else empty (the dock renders empty as a placeholder).
func _scene_label(scene_root: Node) -> String:
	if scene_root == null:
		return ""
	if not scene_root.scene_file_path.is_empty():
		return scene_root.scene_file_path.get_file()
	return scene_root.name


## The bridge URL from GODOT_MCP_BRIDGE_URL or the default ws://127.0.0.1:9080.
func _bridge_url() -> String:
	var url := OS.get_environment("GODOT_MCP_BRIDGE_URL")
	if url.is_empty():
		url = MCPBridge.DEFAULT_URL
	return url


## Server version label: "godot-mcp <version> / Godot <version>".
func _server_version_label() -> String:
	# The Python package version arrives via cmd_server_hello (issue #521),
	# sent by the server right after the cmd_get_addon_info handshake; the
	# router stores it in server_version. Until it lands, show Godot only.
	var gv := Engine.get_version_info()
	var godot_ver := "Godot %d.%d.%s" % [int(gv.get("major", 0)), int(gv.get("minor", 0)), str(gv.get("patch", ""))]
	if _server_version.is_empty():
		return godot_ver
	return "godot-mcp %s / %s" % [_server_version, godot_ver]


## Handle command completion: update the dock's command statistics with the
## handler execution time from the bridge (#520: exec is the one honest number
## the addon can measure — the latency field was dead code reporting exec).
func _on_command_completed(command: String, exec_ms: float) -> void:
	_dock.set_command_stats(_dock.get_command_count(), exec_ms)
	if command == "cmd_write_script" or command == "cmd_patch_script":
		# #417: a script write may introduce a new ``class_name`` global. The
		# parser's global class cache only refreshes on a filesystem scan, so
		# without one the agent's next get_parse_errors reports transient
		# "Could not find type" errors for correct code. Deferred (next frame)
		# and idempotent: scan() is re-entrant-unsafe against the command
		# handler that just returned, and consecutive writes coalesce.
		_rescan_after_script_write.call_deferred()


func _rescan_after_script_write() -> void:
	EditorInterface.get_resource_filesystem().scan()
