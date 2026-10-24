extends SceneTree
## Headless entry point for project validation (#758).
##
## The server runs this with `--headless --path <project> --script <this
## script>`; it prints one `GODOT_MCP_VALIDATION <json>` line and quits.

const Validation := preload("validation.gd")


func _init() -> void:
	var include_warnings := OS.get_cmdline_user_args().has("--include-warnings")
	var result: Dictionary = Validation.run(
		ProjectSettings.globalize_path("res://"), include_warnings
	)
	print("GODOT_MCP_VALIDATION " + JSON.stringify(result))
	quit()
