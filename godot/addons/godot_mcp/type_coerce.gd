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
			return str(value)
		_:
			# Primitives (null, bool, int, float, String) are already JSON-safe.
			return value
