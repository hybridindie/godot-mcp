@tool
extends EditorPlugin
## godot-mcp EditorPlugin entry point.
##
## This is the ONLY layer that touches the Godot Editor API. It will run a
## TCPServer + WebSocketPeer, route incoming JSON command envelopes through a
## single command router to cmd_<verb>_<noun> handlers, and show a read-only
## status dock.
##
## Scaffold stub (issue #1): only the plugin lifecycle is wired so the plugin
## enables/disables cleanly. The status dock lands in issue #2 and the
## WebSocket bridge in issue #3 — those introduce the volatile editor APIs
## (TCPServer, WebSocketPeer, EditorInterface) that MUST be verified against the
## Godot 4.4 docs before use (see .claude/rules/addon.md).

const PLUGIN_NAME := "godot_mcp"


func _enter_tree() -> void:
	# Initialization of the plugin goes here (dock + bridge added in #2/#3).
	pass


func _exit_tree() -> void:
	# Clean-up of the plugin goes here; must leave the editor leak-free.
	pass


func _get_plugin_name() -> String:
	return PLUGIN_NAME
