@tool
class_name MCPTypeCoerce
extends RefCounted
## JSON-safe coercion of Godot types (issue #5; extended for write/roundtrip in #6).
##
## Everything crossing the bridge must be JSON-safe — no Godot objects
## (see .claude/rules/addon.md). This is the single place that knows how Godot
## types map to JSON; never coerce inline. Read direction (Godot → JSON) only for
## now; from_json() lands with the mutation tools (#6).
##
## Shapes (documented in docs/architecture.md):
##   Vector2 → {x, y}      Vector3 → {x, y, z}
##   Color   → {r, g, b, a}  Rect2  → {position:{x,y}, size:{x,y}}
##   NodePath → string       Resource → its resource_path (or class name)
##   Arrays/Dictionaries are coerced element-wise; primitives pass through.


static func to_json(value: Variant) -> Variant:
	match typeof(value):
		TYPE_VECTOR2, TYPE_VECTOR2I:
			return {"x": value.x, "y": value.y}
		TYPE_VECTOR3, TYPE_VECTOR3I:
			return {"x": value.x, "y": value.y, "z": value.z}
		TYPE_COLOR:
			return {"r": value.r, "g": value.g, "b": value.b, "a": value.a}
		TYPE_RECT2, TYPE_RECT2I:
			return {"position": to_json(value.position), "size": to_json(value.size)}
		TYPE_NODE_PATH, TYPE_STRING_NAME:
			return str(value)
		TYPE_ARRAY, TYPE_PACKED_STRING_ARRAY, TYPE_PACKED_INT32_ARRAY, \
		TYPE_PACKED_INT64_ARRAY, TYPE_PACKED_FLOAT32_ARRAY, TYPE_PACKED_FLOAT64_ARRAY:
			var out: Array = []
			for item in value:
				out.append(to_json(item))
			return out
		TYPE_DICTIONARY:
			var out: Dictionary = {}
			for key in value:
				out[str(key)] = to_json(value[key])
			return out
		TYPE_OBJECT:
			if value == null:
				return null
			if value is Resource and not value.resource_path.is_empty():
				return value.resource_path
			# Stable fallback: the class name, never str() (which leaks instance ids).
			return value.get_class()
		_:
			# Primitives (null, bool, int, float, String) are already JSON-safe.
			return value


## JSON → Godot value of the given Variant.Type (issue #6, write direction).
## Vectors/Color accept either the dict form to_json emits ({x, y}) or an array
## ([x, y]); NodePath/StringName from string; primitives coerced to the type.
static func from_json(value: Variant, type: int) -> Variant:
	match type:
		TYPE_VECTOR2:
			return Vector2(_component(value, "x", 0), _component(value, "y", 1))
		TYPE_VECTOR2I:
			return Vector2i(_component(value, "x", 0), _component(value, "y", 1))
		TYPE_VECTOR3:
			return Vector3(
				_component(value, "x", 0), _component(value, "y", 1), _component(value, "z", 2)
			)
		TYPE_VECTOR3I:
			return Vector3i(
				_component(value, "x", 0), _component(value, "y", 1), _component(value, "z", 2)
			)
		TYPE_COLOR:
			return Color(
				_component(value, "r", 0),
				_component(value, "g", 1),
				_component(value, "b", 2),
				_component(value, "a", 3, 1.0),
			)
		TYPE_RECT2:
			if not _has_rect_keys(value):
				return Rect2()
			return Rect2(from_json(value["position"], TYPE_VECTOR2), from_json(value["size"], TYPE_VECTOR2))
		TYPE_RECT2I:
			if not _has_rect_keys(value):
				return Rect2i()
			return Rect2i(from_json(value["position"], TYPE_VECTOR2I), from_json(value["size"], TYPE_VECTOR2I))
		TYPE_NODE_PATH:
			return NodePath(str(value))
		TYPE_STRING_NAME:
			return StringName(str(value))
		TYPE_INT:
			return int(value)
		TYPE_FLOAT:
			return float(value)
		TYPE_BOOL:
			return bool(value)
		TYPE_STRING:
			return str(value)
		_:
			return value


static func _has_rect_keys(value: Variant) -> bool:
	return value is Dictionary and value.has("position") and value.has("size")


## Read a vector/color component from a dict ({"x": ...}) or array ([...]).
static func _component(value: Variant, key: String, index: int, default: float = 0.0) -> float:
	if value is Dictionary:
		return float(value.get(key, default))
	if value is Array and index < value.size():
		return float(value[index])
	return default
