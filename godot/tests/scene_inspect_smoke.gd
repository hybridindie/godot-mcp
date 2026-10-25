@tool
extends SceneTree
## Headless behavior test for the pure scene_inspect helpers (#800).
##
## Run via: godot --headless --path godot/ --script res://tests/scene_inspect_smoke.gd
## Covers `normalize_node_path`, the one helper every node-targeted command goes
## through. Wired into pytest via tests/integration/test_addon_read_smokes.py.

const Inspect := preload("res://addons/godot_mcp/scene_inspect.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	# [input, expected] — leading "/" and a leading "root/" are stripped once,
	# in that order; empty normalizes to the root (".").
	var cases := [
		["Player", "Player"],
		["/Player", "Player"],
		["root/Player", "Player"],
		["/root/Player", "Player"],
		["", "."],
		["Player/Gun", "Player/Gun"],
		["root/Player/Gun", "Player/Gun"],
		["/root/Player/Gun", "Player/Gun"],
		["root", "root"],
	]
	for case in cases:
		var got: String = Inspect.normalize_node_path(case[0])
		if got != case[1]:
			failures.append(
				"normalize_node_path(%s) = %s, expected %s" % [case[0], got, case[1]]
			)

	if failures.is_empty():
		print("SCENE_INSPECT_TEST_OK")
		quit(0)
	else:
		for failure in failures:
			printerr("FAIL: %s" % failure)
		print("SCENE_INSPECT_TEST_FAIL")
		quit(1)
