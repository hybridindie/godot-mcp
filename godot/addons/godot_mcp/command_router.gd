@tool
class_name MCPCommandRouter
extends RefCounted
## Routes incoming command envelopes to cmd_* handlers (issue #3).
##
## Pure dispatch with no networking, so it is verifiable headlessly
## (see godot/tests/bridge_smoke.gd). Every outcome is a JSON-safe response
## envelope — { id, ok, result } on success, { id, ok:false, error, hint } on
## failure — never a raw error or a crash (see .claude/rules/error-handling.md).
##
## Handlers are named cmd_<verb>_<noun>; the matching MCP tool drops the cmd_
## prefix. Mutation handlers (issue #6) register UndoRedo; only ping exists now.

var _handlers: Dictionary = {}


func _init() -> void:
	_handlers["ping"] = _cmd_ping


## Dispatch one envelope ({ id, command, params }) and return a response envelope.
func handle(envelope: Dictionary) -> Dictionary:
	var id := str(envelope.get("id", ""))
	if not envelope.has("command"):
		return _error(id, "VALIDATION_ERROR", "Envelope is missing 'command'.")

	var command := str(envelope["command"])
	if not _handlers.has(command):
		return _error(id, "VALIDATION_ERROR", "Unknown command '%s'." % command)

	# params is untrusted JSON: reject anything that is not an object.
	var raw_params: Variant = envelope.get("params", {})
	if typeof(raw_params) != TYPE_DICTIONARY:
		return _error(id, "VALIDATION_ERROR", "'params' must be an object.")

	var handler: Callable = _handlers[command]
	return _ok(id, handler.call(raw_params as Dictionary))


func has_command(command: String) -> bool:
	return _handlers.has(command)


# --- handlers --------------------------------------------------------------

func _cmd_ping(_params: Dictionary) -> Dictionary:
	return {"pong": true}


# --- envelope builders -----------------------------------------------------

func _ok(id: String, result: Dictionary) -> Dictionary:
	return {"id": id, "ok": true, "result": result}


func _error(id: String, code: String, hint: String) -> Dictionary:
	return {"id": id, "ok": false, "error": code, "hint": hint}
