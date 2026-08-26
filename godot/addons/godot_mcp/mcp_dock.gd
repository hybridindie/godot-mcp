@tool
class_name MCPStatusDock
extends VBoxContainer
## godot-mcp status dock — read-only editor presence (issue #2).
##
## A dumb, editor-independent Control: it holds no Godot Editor API knowledge and
## never mutates the project. The EditorPlugin (godot_mcp.gd) feeds it live state
## through the public setters below. Keeping it editor-free makes it verifiable
## headlessly (see godot/tests/dock_smoke.gd).
##
## Displays: color-coded connection status, server/Godot version, bridge URL,
## active scene, selected node, enabled toolsets, command statistics (total +
## last time), and a recent-command log.

enum ConnectionStatus { DISCONNECTED, CONNECTING, CONNECTED }

const MAX_LOG_ENTRIES := 10
const PLACEHOLDER := "(none)"
const _UNKNOWN := "(unknown)"

const _CONNECTION_TEXT := {
	ConnectionStatus.DISCONNECTED: "Disconnected",
	ConnectionStatus.CONNECTING: "Connecting…",
	ConnectionStatus.CONNECTED: "Connected",
}

const _CONNECTION_COLOR := {
	ConnectionStatus.DISCONNECTED: Color(0.9, 0.3, 0.3),
	ConnectionStatus.CONNECTING: Color(0.9, 0.7, 0.2),
	ConnectionStatus.CONNECTED: Color(0.3, 0.8, 0.3),
}

var _status_dot: ColorRect
var _connection_value: Label
var _version_value: Label
var _bridge_value: Label
var _project_value: Label
var _scene_value: Label
var _selected_value: Label
var _toolsets_value: Label
var _cmd_count_value: Label
var _last_cmd_value: Label
var _log_value: Label
var _recent: PackedStringArray = PackedStringArray()
var _command_count := 0
var _last_command_time := ""


func _init() -> void:
	# Build the UI eagerly so the dock is usable whether or not it is in the tree
	# (the headless test exercises it detached from any scene tree).
	name = "MCP"
	add_theme_constant_override("separation", 6)

	# --- Status header (color dot + connection text) ---
	var status_row := HBoxContainer.new()
	_status_dot = ColorRect.new()
	_status_dot.custom_minimum_size = Vector2(12, 12)
	_status_dot.color = _CONNECTION_COLOR[ConnectionStatus.DISCONNECTED]
	status_row.add_child(_status_dot)
	_connection_value = Label.new()
	_connection_value.text = "Disconnected"
	status_row.add_child(_connection_value)
	add_child(status_row)

	# --- Info fields ---
	_version_value = _add_field("Server:")
	_bridge_value = _add_field("Bridge:")
	_project_value = _add_field("Project:")
	_scene_value = _add_field("Scene:")
	_selected_value = _add_field("Selected:")
	_toolsets_value = _add_field("Toolsets:")

	# --- Command stats ---
	var stats_title := Label.new()
	stats_title.text = "Command statistics"
	stats_title.add_theme_font_size_override("font_size", 12)
	add_child(stats_title)
	_cmd_count_value = _add_field("Total:")
	_last_cmd_value = _add_field("Last:")

	# --- Recent commands log ---
	var log_title := Label.new()
	log_title.text = "Recent commands"
	log_title.add_theme_font_size_override("font_size", 12)
	add_child(log_title)
	_log_value = Label.new()
	_log_value.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_log_value.add_theme_font_size_override("font_size", 11)
	add_child(_log_value)

	# Sensible defaults before the plugin pushes real state.
	set_connection_status(ConnectionStatus.DISCONNECTED)
	set_server_version("")
	set_bridge_url("")
	set_project_path("")
	set_active_scene("")
	set_selected_node("")
	set_enabled_toolsets([])
	set_command_stats(0, "")


## Add a "label: value" row and return the value Label for later updates.
func _add_field(caption: String) -> Label:
	var row := HBoxContainer.new()
	var caption_label := Label.new()
	caption_label.text = caption
	caption_label.add_theme_font_size_override("font_size", 12)
	var value_label := Label.new()
	value_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	value_label.add_theme_font_size_override("font_size", 12)
	row.add_child(caption_label)
	row.add_child(value_label)
	add_child(row)
	return value_label


func set_connection_status(status: ConnectionStatus) -> void:
	_connection_value.text = _CONNECTION_TEXT.get(status, _UNKNOWN)
	_status_dot.color = _CONNECTION_COLOR.get(status, Color.GRAY)


func set_server_version(version: String) -> void:
	_version_value.text = version if not version.is_empty() else _UNKNOWN


func set_bridge_url(url: String) -> void:
	_bridge_value.text = url if not url.is_empty() else _UNKNOWN


func set_project_path(path: String) -> void:
	_project_value.text = path if not path.is_empty() else _UNKNOWN


func set_active_scene(scene_name: String) -> void:
	_scene_value.text = scene_name if not scene_name.is_empty() else PLACEHOLDER


func set_selected_node(node_name: String) -> void:
	_selected_value.text = node_name if not node_name.is_empty() else PLACEHOLDER


func set_enabled_toolsets(toolsets: PackedStringArray) -> void:
	if toolsets.is_empty():
		_toolsets_value.text = PLACEHOLDER
	else:
		_toolsets_value.text = ", ".join(toolsets)


func set_command_stats(count: int, last_time: String) -> void:
	_cmd_count_value.text = str(count)
	_last_cmd_value.text = last_time if not last_time.is_empty() else PLACEHOLDER


## Append a command to the recent log, keeping only the last MAX_LOG_ENTRIES.
func log_command(entry: String) -> void:
	_recent.append(entry)
	while _recent.size() > MAX_LOG_ENTRIES:
		_recent.remove_at(0)
	_log_value.text = "\n".join(_recent)
	_command_count += 1
	_last_command_time = Time.get_time_string_from_system()
	set_command_stats(_command_count, _last_command_time)


func get_recent_commands() -> PackedStringArray:
	# Return a copy so callers cannot mutate the dock's state behind its back.
	return _recent.duplicate()


func get_command_count() -> int:
	return _command_count


# --- Accessors used by the headless dock test to assert the labels updated. ---

func displayed_connection() -> String:
	return _connection_value.text


func displayed_server_version() -> String:
	return _version_value.text


func displayed_bridge_url() -> String:
	return _bridge_value.text


func displayed_project() -> String:
	return _project_value.text


func displayed_scene() -> String:
	return _scene_value.text


func displayed_selected() -> String:
	return _selected_value.text


func displayed_toolsets() -> String:
	return _toolsets_value.text


func displayed_command_count() -> String:
	return _cmd_count_value.text


func displayed_log() -> String:
	return _log_value.text