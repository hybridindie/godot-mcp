extends SceneTree
## Headless entry point for project validation (#758).
##
## The server runs this with `--headless --path <project> --script <this
## script>`; it prints one `GODOT_MCP_VALIDATION <json>` line and quits.

const Validation := preload("validation.gd")


func _init() -> void:
	var result: Dictionary = Validation.run(ProjectSettings.globalize_path("res://"), true)
	print("GODOT_MCP_VALIDATION " + JSON.stringify(result))
	quit()
