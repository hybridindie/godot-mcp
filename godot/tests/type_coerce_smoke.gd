@tool
extends SceneTree
## Headless behavior test for MCPTypeCoerce (issue #524).
##
## Run via: godot --headless --path godot/ --script res://tests/type_coerce_smoke.gd
## Exercises the pure-logic coercion layer — every JSON shape in
## docs/site/reference-value-shapes.md, both directions, string-form parsing,
## and the error paths of object_from_json — with no editor and no networking,
## deterministically. Wired into pytest via
## tests/integration/test_addon_read_smokes.py (issue #524).

const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")

var _failures: Array[String] = []


func _check(name: String, actual: Variant, expected: Variant) -> void:
	# Deep, float-tolerant equality handles every JSON-safe shape uniformly.
	if not _json_equal(actual, expected):
		_failures.append("%s: expected %s, got %s" % [name, str(expected), str(actual)])


## Deep equality on the JSON-safe shapes type_coerce produces (float-tolerant).
func _json_equal(a: Variant, b: Variant) -> bool:
	if typeof(a) != typeof(b):
		return false
	match typeof(a):
		TYPE_ARRAY:
			var aa := a as Array
			var bb := b as Array
			if aa.size() != bb.size():
				return false
			for i in aa.size():
				if not _json_equal(aa[i], bb[i]):
					return false
			return true
		TYPE_DICTIONARY:
			var da := a as Dictionary
			var db := b as Dictionary
			if da.size() != db.size():
				return false
			for key in da:
				if not db.has(key) or not _json_equal(da[key], db[key]):
					return false
			return true
		TYPE_FLOAT:
			return absf(a - b) < 1e-6
		_:
			return a == b


func _test_to_json_shapes() -> void:
	_check("vec2", Coerce.to_json(Vector2(100, 200)), {"x": 100.0, "y": 200.0})
	_check("vec2i", Coerce.to_json(Vector2i(1, 2)), {"x": 1, "y": 2})
	_check("vec3", Coerce.to_json(Vector3(1, 2, 3)), {"x": 1.0, "y": 2.0, "z": 3.0})
	_check("vec4", Coerce.to_json(Vector4(1, 2, 3, 4)), {"x": 1.0, "y": 2.0, "z": 3.0, "w": 4.0})
	_check("color", Coerce.to_json(Color(1, 0, 0, 0.5)), {"r": 1.0, "g": 0.0, "b": 0.0, "a": 0.5})
	_check("rect2", Coerce.to_json(Rect2(0, 0, 4, 5)), {
		"position": {"x": 0.0, "y": 0.0}, "size": {"x": 4.0, "y": 5.0}
	})
	_check("node_path", Coerce.to_json(NodePath("A/B")), "A/B")
	_check("string_name", Coerce.to_json(StringName("hi")), "hi")
	_check("vec2_array", Coerce.to_json([Vector2(1, 2), Vector2(3, 4)]), [
		{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 4.0}
	])
	_check("packed_strings", Coerce.to_json(PackedStringArray(["a", "b"])), ["a", "b"])
	_check("nested_dict", Coerce.to_json({"v": Vector2(0, 0)}), {"v": {"x": 0.0, "y": 0.0}})
	_check("primitives_pass", Coerce.to_json({"b": true, "i": 3, "s": "x"}), {"b": true, "i": 3, "s": "x"})
	_check("null", Coerce.to_json(null), null)


func _test_to_json_object_fallback() -> void:
	# A Resource with a path serializes to its path...
	var res := Resource.new()
	res.resource_path = "res://icon.png"
	_check("resource_path", Coerce.to_json(res), "res://icon.png")
	# ...an object with no path falls back to the class name, never str() (no ids).
	var plain := RefCounted.new()
	_check("class_fallback", Coerce.to_json(plain), "RefCounted")


func _test_from_json_dict_and_array_forms() -> void:
	_check("vec2_dict", Coerce.from_json({"x": 1, "y": 2}, TYPE_VECTOR2), Vector2(1, 2))
	_check("vec2_arr", Coerce.from_json([3, 4], TYPE_VECTOR2), Vector2(3, 4))
	_check("vec3_dict", Coerce.from_json({"x": 1, "y": 2, "z": 3}, TYPE_VECTOR3), Vector3(1, 2, 3))
	_check("vec3i_arr", Coerce.from_json([1, 2, 3], TYPE_VECTOR3I), Vector3i(1, 2, 3))
	_check("vec4_dict", Coerce.from_json({"x": 1, "y": 2, "z": 3, "w": 4}, TYPE_VECTOR4), Vector4(1, 2, 3, 4))
	_check("color_dict", Coerce.from_json({"r": 1, "g": 0, "b": 0, "a": 1}, TYPE_COLOR), Color(1, 0, 0))
	_check("color_missing_alpha_defaults_opaque", Coerce.from_json({"r": 0, "g": 0, "b": 0}, TYPE_COLOR), Color(0, 0, 0))
	_check("rect2_dict", Coerce.from_json({"position": [0, 0], "size": [4, 5]}, TYPE_RECT2), Rect2(0, 0, 4, 5))
	_check("rect2i_dict", Coerce.from_json({"position": [0, 0], "size": [2, 2]}, TYPE_RECT2I), Rect2i(0, 0, 2, 2))
	_check("rect2_empty_defaults", Coerce.from_json({}, TYPE_RECT2), Rect2())
	_check("node_path", Coerce.from_json("A/B", TYPE_NODE_PATH), NodePath("A/B"))
	_check("string_name", Coerce.from_json("hi", TYPE_STRING_NAME), StringName("hi"))
	_check("int_from_float", Coerce.from_json(2.5, TYPE_INT), 2)
	_check("float_from_int", Coerce.from_json(2, TYPE_FLOAT), 2.0)
	_check("bool", Coerce.from_json(true, TYPE_BOOL), true)
	_check("string", Coerce.from_json(42, TYPE_STRING), "42")
	_check("missing_components_default_zero", Coerce.from_json({}, TYPE_VECTOR2), Vector2())
	_check("unknown_type_passthrough", Coerce.from_json({"a": 1}, TYPE_DICTIONARY), {"a": 1})


func _test_from_json_string_forms() -> void:
	_check("ctor_vec2", Coerce.from_json("Vector2(100, 200)", TYPE_VECTOR2), Vector2(100, 200))
	_check("ctor_vec3", Coerce.from_json("Vector3(1, 2, 3)", TYPE_VECTOR3), Vector3(1, 2, 3))
	_check("ctor_vec4", Coerce.from_json("Vector4(1, 2, 3, 4)", TYPE_VECTOR4), Vector4(1, 2, 3, 4))
	_check("ctor_rect2", Coerce.from_json("Rect2(0, 0, 4, 5)", TYPE_RECT2), Rect2(0, 0, 4, 5))
	_check("ctor_padded", Coerce.from_json("  Vector2(1, 2)", TYPE_VECTOR2), Vector2(1, 2))
	_check("html_color", Coerce.from_json("#ff0000", TYPE_COLOR), Color(1, 0, 0))
	_check("html_color_alpha", Coerce.from_json("#ff0000ff", TYPE_COLOR), Color(1, 0, 0, 1))
	# A constructor string of the WRONG type parses (str_to_var returns the
	# Vector3) but the typeof() guard rejects it — falls back to the dict path.
	_check("ctor_wrong_type_falls_through", Coerce.from_json("Vector3(1, 2, 3)", TYPE_VECTOR2), Vector2())
	# A plausible-prefix string that isn't parseable falls back to the dict path.
	_check("ctor_garbage", Coerce.from_json("Vector2(oops)", TYPE_VECTOR2), Vector2())
	_check("no_form_for_primitives", Coerce.from_json("7", TYPE_INT), 7)


func _test_object_from_json() -> void:
	# null/missing value = "clear this property" — allowed.
	var clear := Coerce.object_from_json(null)
	if clear.get("ok") != true or clear.get("value") != null:
		_failures.append("object_from_json(null) should clear: %s" % str(clear))
	# A missing resource is a structured RESOURCE_NOT_FOUND.
	var missing := Coerce.object_from_json("res://definitely_not_here.tres")
	if missing.get("ok") != false or missing.get("error") != "RESOURCE_NOT_FOUND":
		_failures.append("missing resource should be RESOURCE_NOT_FOUND: %s" % str(missing))
	if not str(missing.get("hint", "")).contains("definitely_not_here"):
		_failures.append("missing-resource hint should name the path: %s" % str(missing))
	# A non-string, non-null value is not coercible.
	var bad := Coerce.object_from_json(42)
	if bad.get("ok") != false or bad.get("error") != "VALIDATION_ERROR":
		_failures.append("non-string object value should be VALIDATION_ERROR: %s" % str(bad))


func _test_roundtrip() -> void:
	# to_json → from_json restores the same Godot value (the #6 roundtrip contract).
	var vec2 := Vector2(1.5, -2.5)
	if Coerce.from_json(Coerce.to_json(vec2), TYPE_VECTOR2) != vec2:
		_failures.append("vec2 roundtrip")
	var vec3 := Vector3(1, 2, 3)
	if Coerce.from_json(Coerce.to_json(vec3), TYPE_VECTOR3) != vec3:
		_failures.append("vec3 roundtrip")
	var col := Color(0.25, 0.5, 0.75, 1.0)
	var col_back: Color = Coerce.from_json(Coerce.to_json(col), TYPE_COLOR)
	if not _json_equal(col_back, col):
		_failures.append("color roundtrip: %s" % str(col_back))
	var rect := Rect2(1, 2, 3, 4)
	if not _json_equal(Coerce.from_json(Coerce.to_json(rect), TYPE_RECT2), rect):
		_failures.append("rect2 roundtrip")


func _initialize() -> void:
	_test_to_json_shapes()
	_test_to_json_object_fallback()
	_test_from_json_dict_and_array_forms()
	_test_from_json_string_forms()
	_test_object_from_json()
	_test_roundtrip()

	if _failures.is_empty():
		print("TYPE_COERCE_TEST_OK")
		quit(0)
	else:
		for f in _failures:
			printerr("FAIL: %s" % f)
		print("TYPE_COERCE_TEST_FAIL")
		quit(1)