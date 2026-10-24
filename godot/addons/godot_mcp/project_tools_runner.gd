extends SceneTree
## Headless entry point for project-tool discovery (#761).
##
## The server/tests run this with `--headless --path <project> --script <this
## script>`; it prints one `GODOT_MCP_PROJECT_TOOLS <json>` line and quits so CI
## can pin the scanner without an editor.

const ProjectTools := preload("project_tools.gd")


func _init() -> void:
	print("GODOT_MCP_PROJECT_TOOLS " + JSON.stringify(ProjectTools.scan("res://")))
	quit()
