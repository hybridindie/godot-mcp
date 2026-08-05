@tool
extends SceneTree
## Headless behavior test for MCPAnimationRead (issue #218).
##
## Run via: godot --headless --path godot/ --script res://tests/animation_read_smoke.gd
## Builds a real AnimationPlayer + Animation (no EditorInterface) and verifies the
## pure read serialization round-trips against the live Godot Animation API.

const AnimRead := preload("res://addons/godot_mcp/animation_read.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	var player := AnimationPlayer.new()
	var lib := AnimationLibrary.new()
	player.add_animation_library("", lib)

	var 	anim := Animation.new()
	anim.length = 2.0
	anim.loop_mode = Animation.LOOP_LINEAR
	var ti := anim.add_track(Animation.TYPE_VALUE)
	anim.track_set_path(ti, NodePath("Sprite2D:position"))
	anim.track_insert_key(ti, 0.5, Vector2(10, 20))
	lib.add_animation("walk", anim)
	lib.add_animation("idle", Animation.new())

	# names: all animations on the player (sorted by Godot's own order).
	var names: Array = AnimRead.names(player)
	if not ("walk" in names and "idle" in names and names.size() == 2):
		failures.append("names wrong: %s" % str(names))

	# serialize: length, track type/path, and a JSON-coerced keyframe value.
	var detail: Dictionary = AnimRead.serialize("walk", anim)
	_eq(failures, "name", detail.get("name"), "walk")
	_eq(failures, "length", detail.get("length"), 2.0)
	_eq(failures, "loop_mode", detail.get("loop_mode"), "linear")
	var tracks: Array = detail.get("tracks")
	if tracks.size() != 1:
		failures.append("track count: %s" % str(tracks))
	else:
		var t: Dictionary = tracks[0]
		_eq(failures, "type", t.get("type"), "value")
		_eq(failures, "path", t.get("path"), "Sprite2D:position")
		var keys: Array = t.get("keys")
		if keys.size() != 1:
			failures.append("key count: %s" % str(keys))
		else:
			_eq(failures, "key.time", keys[0].get("time"), 0.5)
			_eq(failures, "key.value", keys[0].get("value"), {"x": 10.0, "y": 20.0})

	# Output must be JSON-safe.
	if JSON.stringify(detail) == "":
		failures.append("serialized animation is not JSON-safe")

	player.free()
	if failures.is_empty():
		print("ANIM_READ_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("ANIM_READ_TEST_FAIL")
		quit(1)


func _eq(failures: Array[String], label: String, got: Variant, want: Variant) -> void:
	if got != want:
		failures.append("%s: expected %s, got %s" % [label, str(want), str(got)])
