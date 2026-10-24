@tool
class_name MCPProjectToolHandlers
extends RefCounted
## Domain handler: project-registered tools (#761).
##
## Registered by the router on _init(). Discovery and execution live in
## project_tools.gd; this file is only the bridge surface.

const ProjectTools := preload("../project_tools.gd")

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_scan_project_tools"] = _cmd_scan_project_tools
	handlers["cmd_run_project_tool"] = _cmd_run_project_tool


func _cmd_scan_project_tools(_params: Dictionary) -> Dictionary:
	return _router._ok(ProjectTools.scan("res://"))


func _cmd_run_project_tool(params: Dictionary) -> Dictionary:
	var script_path := str(params.get("script", ""))
	var function_name := str(params.get("function", ""))
	var args: Dictionary = params.get("args", {})
	if script_path.is_empty() or function_name.is_empty():
		return _router._fail(
			"VALIDATION_ERROR",
			"Both 'script' and 'function' are required.",
			"script"
		)
	if not script_path.begins_with("res://"):
		return _router._fail(
			"VALIDATION_ERROR",
			"script must be a res:// path. Got: '%s'" % script_path,
			"script"
		)
	var outcome := ProjectTools.run(script_path, function_name, args)
	if outcome.has("error"):
		return _router._fail(
			str(outcome["error"]),
			str(outcome.get("hint", "Project tool failed.")),
			"project_tool"
		)
	return _router._ok(outcome)
