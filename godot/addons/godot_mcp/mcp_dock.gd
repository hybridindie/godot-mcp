@tool
extends VBoxContainer
## godot-mcp status dock — read-only editor presence (issue #2).
##
## A dumb, editor-independent Control: it holds no Godot Editor API knowledge and
## never mutates the project. The EditorPlugin (godot_mcp.gd) feeds it live state
## through the public setters below. Keeping it editor-free makes it verifiable
## headlessly (see godot/tests/dock_smoke.gd).
##
## The bridge/MCP integration (issues #3+) only ever calls set_connection_status()
## and log_command(); this phase has no networking.

enum ConnectionStatus { DISCONNECTED, CONNECTING, CONNECTED }

const MAX_LOG_ENTRIES := 10
const PLACEHOLDER := "(none)"
const _UNKNOWN := "(unknown)"

const _CONNECTION_TEXT := {
	ConnectionStatus.DISCONNECTED: "Disconnected",
	ConnectionStatus.CONNECTING: "Connecting…",
	ConnectionStatus.CONNECTED: "Connected",
}

var _connection_value: Label
var _project_value: Label
var _scene_value: Label
var _selected_value: Label
var _log_value: Label
var _recent: PackedStringArray = PackedStringArray()


func _init() -> void:
	# Build the UI eagerly so the dock is usable whether or not it is in the tree
	# (the headless test exercises it detached from any scene tree).
	name = "MCP"
	add_theme_constant_override("separation", 6)

	_connection_value = _add_field("Status:")
	_project_value = _add_field("Project:")
	_scene_value = _add_field("Scene:")
	_selected_value = _add_field("Selected:")

	var log_title := Label.new()
	log_title.text = "Recent commands"
	add_child(log_title)
	_log_value = Label.new()
	_log_value.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_log_value)

	# Sensible defaults before the plugin pushes real state.
	set_connection_status(ConnectionStatus.DISCONNECTED)
	set_project_path("")
	set_active_scene("")
	set_selected_node("")


## Add a "label: value" row and return the value Label for later updates.
func _add_field(caption: String) -> Label:
	var row := HBoxContainer.new()
	var caption_label := Label.new()
	caption_label.text = caption
	var value_label := Label.new()
	value_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(caption_label)
	row.add_child(value_label)
	add_child(row)
	return value_label


func set_connection_status(status: ConnectionStatus) -> void:
	_connection_value.text = _CONNECTION_TEXT.get(status, _UNKNOWN)


func set_project_path(path: String) -> void:
	_project_value.text = path if not path.is_empty() else _UNKNOWN


func set_active_scene(scene_name: String) -> void:
	_scene_value.text = scene_name if not scene_name.is_empty() else PLACEHOLDER


func set_selected_node(node_name: String) -> void:
	_selected_value.text = node_name if not node_name.is_empty() else PLACEHOLDER


## Append a command to the recent log, keeping only the last MAX_LOG_ENTRIES.
func log_command(entry: String) -> void:
	_recent.append(entry)
	while _recent.size() > MAX_LOG_ENTRIES:
		_recent.remove_at(0)
	_log_value.text = "\n".join(_recent)


func get_recent_commands() -> PackedStringArray:
	return _recent


# --- Accessors used by the headless dock test to assert the labels updated. ---

func displayed_connection() -> String:
	return _connection_value.text


func displayed_project() -> String:
	return _project_value.text


func displayed_scene() -> String:
	return _scene_value.text


func displayed_selected() -> String:
	return _selected_value.text


func displayed_log() -> String:
	return _log_value.text
