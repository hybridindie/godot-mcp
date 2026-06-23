@tool
extends SceneTree
## Headless behavior test for MCPParticleRead (issue #219 P4).
##
## Run via: godot --headless --path godot/ --script res://tests/particle_read_smoke.gd
## Builds a real ParticleProcessMaterial + GradientTexture1D (no EditorInterface) and
## verifies the pure read serialization against the live Godot API.

const ParticleRead := preload("res://addons/godot_mcp/particle_read.gd")


func _initialize() -> void:
	var failures: Array[String] = []

	# No material → has_material false, empty props, null ramp.
	var none: Dictionary = ParticleRead.serialize(null)
	_eq(failures, "none.has_material", none.get("has_material"), false)
	_eq(failures, "none.color_ramp", none.get("color_ramp"), null)

	# A real material with a couple of props + a color ramp.
	var mat := ParticleProcessMaterial.new()
	mat.spread = 45.0
	var gradient := Gradient.new()
	gradient.offsets = PackedFloat32Array([0.0, 1.0])
	gradient.colors = PackedColorArray([Color(1, 1, 1, 1), Color(1, 0, 0, 0)])
	var tex := GradientTexture1D.new()
	tex.gradient = gradient
	mat.color_ramp = tex

	var data: Dictionary = ParticleRead.serialize(mat)
	_eq(failures, "has_material", data.get("has_material"), true)
	var props: Dictionary = data.get("properties")
	_eq(failures, "props.spread", props.get("spread"), 45.0)
	# color_ramp is serialized as gradient stops, never as a sub-resource ref.
	if props.has("color_ramp"):
		failures.append("color_ramp leaked into properties")
	var ramp: Dictionary = data.get("color_ramp")
	_eq(failures, "ramp.offsets", ramp.get("offsets"), [0.0, 1.0])
	var colors: Array = ramp.get("colors")
	if colors.size() != 2:
		failures.append("ramp colors size: %s" % str(colors))
	else:
		_eq(failures, "ramp.color0", colors[0], {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0})
		_eq(failures, "ramp.color1.a", colors[1].get("a"), 0.0)

	# Output must be JSON-safe.
	if JSON.stringify(data) == "":
		failures.append("serialized material is not JSON-safe")

	if failures.is_empty():
		print("PARTICLE_READ_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("PARTICLE_READ_TEST_FAIL")
		quit(1)


func _eq(failures: Array[String], label: String, got: Variant, want: Variant) -> void:
	if got != want:
		failures.append("%s: expected %s, got %s" % [label, str(want), str(got)])
