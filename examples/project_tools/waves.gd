@tool
extends RefCounted
## Example project tools (#761).
##
## Copy this file into your project (outside `res://addons/`), enable the
## `project` toolset, and call `godot_project_scan_tools()`. Each annotated
## function is registered as `godot_project_<script stem>_<function>`.

enum Kind { ENEMY, BOSS }


## Spawn a wave of enemies and return how many were requested.
## @mcp_tool safety=read_only
func wave_size(count: int, kind: Kind = Kind.ENEMY) -> Dictionary:
	return {"count": count, "boss": kind == Kind.BOSS}


## Record a spawned wave. Mutating: supports dry_run=True.
## @mcp_tool safety=mutating
func record_wave(count: int, label: String = "wave") -> Dictionary:
	return {"recorded": count, "label": label}


## Clear the wave log. Destructive: requires confirm=True.
## @mcp_tool safety=destructive
func clear_wave_log() -> Dictionary:
	return {"cleared": true}
