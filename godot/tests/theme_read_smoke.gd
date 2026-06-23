@tool
extends SceneTree
## Headless behavior test for MCPThemeRead (issue #219 G7).
##
## Run via: godot --headless --path godot/ --script res://tests/theme_read_smoke.gd
## Builds a real Control with color / font-size / stylebox overrides (no EditorInterface)
## and verifies the pure read serialization against the live Godot theme API.

const ThemeRead := preload("res://addons/godot_mcp/theme_read.gd")


func _initialize() -> void:
	var failures: Array[String] = []

	# A Label with no overrides → all three buckets empty. (A real control type is used
	# because overrides only surface in get_property_list for items the control defines.)
	var bare := Label.new()
	var empty: Dictionary = ThemeRead.overrides(bare)
	if not (empty["colors"] as Dictionary).is_empty():
		failures.append("bare colors not empty")
	if not (empty["font_sizes"] as Dictionary).is_empty():
		failures.append("bare font_sizes not empty")
	if not (empty["styleboxes"] as Array).is_empty():
		failures.append("bare styleboxes not empty")
	bare.free()

	# A Label carrying one override of each kind (font_color / font_size / the "normal"
	# stylebox are all real Label theme items).
	var node := Label.new()
	node.add_theme_color_override("font_color", Color(1, 0, 0, 1))
	node.add_theme_font_size_override("font_size", 24)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.1, 0.1, 0.1, 1)
	node.add_theme_stylebox_override("normal", sb)

	var data: Dictionary = ThemeRead.overrides(node)
	var colors: Dictionary = data["colors"]
	_eq(failures, "colors.font_color", colors.get("font_color"), {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0})
	var font_sizes: Dictionary = data["font_sizes"]
	_eq(failures, "font_sizes.font_size", font_sizes.get("font_size"), 24)
	var styleboxes: Array = data["styleboxes"]
	if styleboxes.size() != 1:
		failures.append("styleboxes size: %s" % str(styleboxes))
	else:
		var entry: Dictionary = styleboxes[0]
		_eq(failures, "stylebox.name", entry.get("name"), "normal")
		_eq(failures, "stylebox.type", entry.get("type"), "StyleBoxFlat")
		var props: Dictionary = entry.get("properties")
		# bg_color round-trips through type_coerce so the StyleBox can be recreated.
		if not props.has("bg_color"):
			failures.append("stylebox properties missing bg_color: %s" % str(props.keys()))

	# Output must be JSON-safe.
	if JSON.stringify(data) == "":
		failures.append("serialized overrides are not JSON-safe")
	node.free()

	if failures.is_empty():
		print("THEME_READ_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("THEME_READ_TEST_FAIL")
		quit(1)


func _eq(failures: Array[String], label: String, got: Variant, want: Variant) -> void:
	if got != want:
		failures.append("%s: expected %s, got %s" % [label, str(want), str(got)])
