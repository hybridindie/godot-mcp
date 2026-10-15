@tool
extends Logger
## Game-output relay logger for the runtime probe (issue #534).
##
## Kept in its OWN script (no `class_name`) because `Logger` and `OS.add_logger`
## are Godot 4.5+ (issue #648): the probe `load()`s this file only when
## `OS.has_method("add_logger")`, so on the 4.4 floor this script is never parsed
## and the probe still parses/loads (output capture just degrades to an empty
## ring). Do NOT add a `class_name` — the editor would then parse it eagerly on
## 4.4 and break the whole addon.
##
## The sink Callable relays into the probe's mutex-guarded ring; it is invoked
## from arbitrary threads (Godot's logging contract), so the probe side locks.

var _sink: Callable


func _init(sink: Callable) -> void:
	_sink = sink


func _log_message(message: String, error: bool) -> void:
	_sink.call(message, "error" if error else "stdout")


func _log_error(
	function: String, file: String, line: int, code: String, rationale: String,
	editor_notify: bool, error_type: int, script_backtraces: Array
) -> void:
	var kind := "error"
	if error_type == Logger.ERROR_TYPE_WARNING:
		kind = "warning"
	# `rationale` carries the human text for push_error/push_warning/script errors;
	# `code` is the engine-side message. Prefer whichever is present.
	var text := rationale
	if text.is_empty():
		text = code
	if text.is_empty():
		text = "%s @ %s:%d" % [function, file, line]
	_sink.call(text, kind)
