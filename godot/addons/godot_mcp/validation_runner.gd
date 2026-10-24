extends SceneTree
## Headless entry point for project validation (#758).
##
## The server runs this with `--headless --path <project> --script <this
## script>`; it prints one `GODOT_MCP_VALIDATION <json>` line and quits.

const Validation := preload("validation.gd")


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var include_warnings := args.has("--include-warnings")
	var scopes: Array = []
	for arg in args:
		if str(arg).begins_with("--scope="):
			scopes.append(str(arg).trim_prefix("--scope="))
	var result: Dictionary = Validation.run(
		ProjectSettings.globalize_path("res://"), include_warnings, scopes
	)
	print("GODOT_MCP_VALIDATION " + JSON.stringify(result))
	quit()
