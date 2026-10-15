@tool
class_name MCPTypeCoerce
extends RefCounted
## JSON-safe coercion of Godot types (issue #5; extended for write/roundtrip in #6).
##
## Everything crossing the bridge must be JSON-safe — no Godot objects
## (see .opencode/rules/addon.md). This is the single place that knows how Godot
## types map to JSON; never coerce inline. The runtime probe reuses this module
## (issue #641) so the editor and the running game emit identical shapes.
##
## Shapes (documented in docs/site/reference-value-shapes.md):
##   Vector2 → {x, y}      Vector3 → {x, y, z}      Vector4 → {x, y, z, w}
##   Color   → {r, g, b, a}  Rect2  → {position:{x,y}, size:{x,y}}
##   Quaternion → {x,y,z,w}  AABB → {position, size}  Plane → {normal:{x,y,z}, d}
##   Basis → {x, y, z}       Transform2D → {x, y, origin}
##   Transform3D → {basis, origin}   Projection → {x, y, z, w}
##   PackedByteArray → [int]  Packed{Vector2,Vector3,Color}Array → [shape]
##   NodePath → string       Resource → its resource_path (or class name)
##   NaN/INF → "__nan__"/"__inf__"/"__-inf__" (no JSON literal exists)
##   Arrays/Dictionaries are coerced element-wise; primitives pass through.

# Non-finite floats have no JSON representation; JSON.stringify maps NaN→null and
# INF→1e99999 (lossy). Encode them explicitly so a round-trip is faithful (#641).
const NAN_SENTINEL := "__nan__"
const INF_SENTINEL := "__inf__"
const NINF_SENTINEL := "__-inf__"


## A float as a JSON-safe value: itself, or a sentinel string for NaN/±INF (#641).
static func _json_float(f: float) -> Variant:
	if is_nan(f):
		return NAN_SENTINEL
	if is_inf(f):
		return INF_SENTINEL if f > 0.0 else NINF_SENTINEL
	return f


## A JSON value as a float, decoding the NaN/±INF sentinels (#641).
static func _float_from(value: Variant) -> float:
	if value is String:
		match value:
			NAN_SENTINEL:
				return NAN
			INF_SENTINEL:
				return INF
			NINF_SENTINEL:
				return -INF
	return float(value)


static func to_json(value: Variant) -> Variant:
	match typeof(value):
		TYPE_FLOAT:
			return _json_float(value)
		TYPE_VECTOR2:
			return {"x": _json_float(value.x), "y": _json_float(value.y)}
		TYPE_VECTOR2I:
			return {"x": value.x, "y": value.y}
		TYPE_VECTOR3:
			return {"x": _json_float(value.x), "y": _json_float(value.y), "z": _json_float(value.z)}
		TYPE_VECTOR3I:
			return {"x": value.x, "y": value.y, "z": value.z}
		TYPE_VECTOR4:
			return {
				"x": _json_float(value.x), "y": _json_float(value.y),
				"z": _json_float(value.z), "w": _json_float(value.w),
			}
		TYPE_VECTOR4I:
			return {"x": value.x, "y": value.y, "z": value.z, "w": value.w}
		TYPE_COLOR:
			return {
				"r": _json_float(value.r), "g": _json_float(value.g),
				"b": _json_float(value.b), "a": _json_float(value.a),
			}
		TYPE_RECT2, TYPE_RECT2I:
			return {"position": to_json(value.position), "size": to_json(value.size)}
		TYPE_QUATERNION:
			return {
				"x": _json_float(value.x), "y": _json_float(value.y),
				"z": _json_float(value.z), "w": _json_float(value.w),
			}
		TYPE_AABB:
			return {"position": to_json(value.position), "size": to_json(value.size)}
		TYPE_PLANE:
			return {"normal": to_json(value.normal), "d": _json_float(value.d)}
		TYPE_BASIS:
			return {"x": to_json(value.x), "y": to_json(value.y), "z": to_json(value.z)}
		TYPE_TRANSFORM2D:
			return {"x": to_json(value.x), "y": to_json(value.y), "origin": to_json(value.origin)}
		TYPE_TRANSFORM3D:
			return {"basis": to_json(value.basis), "origin": to_json(value.origin)}
		TYPE_PROJECTION:
			return {
				"x": to_json(value.x), "y": to_json(value.y),
				"z": to_json(value.z), "w": to_json(value.w),
			}
		TYPE_NODE_PATH, TYPE_STRING_NAME:
			return str(value)
		TYPE_ARRAY, TYPE_PACKED_BYTE_ARRAY, TYPE_PACKED_STRING_ARRAY, TYPE_PACKED_INT32_ARRAY, \
		TYPE_PACKED_INT64_ARRAY, TYPE_PACKED_FLOAT32_ARRAY, TYPE_PACKED_FLOAT64_ARRAY, \
		TYPE_PACKED_VECTOR2_ARRAY, TYPE_PACKED_VECTOR3_ARRAY, TYPE_PACKED_COLOR_ARRAY:
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
			# Primitives (null, bool, int, String) are already JSON-safe.
			return value


## JSON → Godot value of the given Variant.Type (issue #6, write direction).
## Vectors/Color accept either the dict form to_json emits ({x, y}) or an array
## ([x, y]); NodePath/StringName from string; primitives coerced to the type.
##
## Composite types also accept agent-friendly string forms (issue #51):
##   "Vector2(100, 200)", "Vector3(1, 2, 3)", "Vector4(1, 2, 3, 4)", "Rect2(0, 0, 4, 5)"
##   (via str_to_var)
##   and HTML/hex colors "#ff0000" / "#ff0000ff" (via Color.html).
static func from_json(value: Variant, type: int) -> Variant:
	if value is String:
		var parsed: Variant = _from_string(value, type)
		if parsed != null:
			return parsed
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
		TYPE_VECTOR4:
			return Vector4(
				_component(value, "x", 0), _component(value, "y", 1),
				_component(value, "z", 2), _component(value, "w", 3)
			)
		TYPE_VECTOR4I:
			return Vector4i(
				_component(value, "x", 0), _component(value, "y", 1),
				_component(value, "z", 2), _component(value, "w", 3)
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
		TYPE_QUATERNION:
			return Quaternion(
				_component(value, "x", 0), _component(value, "y", 1),
				_component(value, "z", 2), _component(value, "w", 3, 1.0),
			)
		TYPE_AABB:
			if not _has_rect_keys(value):
				return AABB()
			return AABB(from_json(value["position"], TYPE_VECTOR3), from_json(value["size"], TYPE_VECTOR3))
		TYPE_PLANE:
			if not (value is Dictionary and (value as Dictionary).has("normal")):
				return Plane()
			return Plane(
				from_json(value["normal"], TYPE_VECTOR3),
				_float_from((value as Dictionary).get("d", 0.0)),
			)
		TYPE_BASIS:
			if not _has_xyz_keys(value):
				return Basis()
			return Basis(
				from_json(value["x"], TYPE_VECTOR3), from_json(value["y"], TYPE_VECTOR3),
				from_json(value["z"], TYPE_VECTOR3)
			)
		TYPE_TRANSFORM2D:
			if not _has_cols(value, ["x", "y", "origin"]):
				return Transform2D()
			return Transform2D(
				from_json(value["x"], TYPE_VECTOR2), from_json(value["y"], TYPE_VECTOR2),
				from_json(value["origin"], TYPE_VECTOR2)
			)
		TYPE_TRANSFORM3D:
			if not _has_cols(value, ["basis", "origin"]):
				return Transform3D()
			return Transform3D(
				from_json(value["basis"], TYPE_BASIS), from_json(value["origin"], TYPE_VECTOR3)
			)
		TYPE_PROJECTION:
			if not _has_cols(value, ["x", "y", "z", "w"]):
				return Projection()
			return Projection(
				from_json(value["x"], TYPE_VECTOR4), from_json(value["y"], TYPE_VECTOR4),
				from_json(value["z"], TYPE_VECTOR4), from_json(value["w"], TYPE_VECTOR4)
			)
		TYPE_PACKED_BYTE_ARRAY:
			var pba := PackedByteArray()
			if value is Array:
				for v in value:
					pba.append(int(v))
			return pba
		TYPE_PACKED_INT32_ARRAY:
			return PackedInt32Array(value if value is Array else [])
		TYPE_PACKED_INT64_ARRAY:
			return PackedInt64Array(value if value is Array else [])
		TYPE_PACKED_FLOAT32_ARRAY:
			return PackedFloat32Array(value if value is Array else [])
		TYPE_PACKED_FLOAT64_ARRAY:
			return PackedFloat64Array(value if value is Array else [])
		TYPE_PACKED_STRING_ARRAY:
			return PackedStringArray(value if value is Array else [])
		TYPE_PACKED_VECTOR2_ARRAY:
			var pv2 := PackedVector2Array()
			if value is Array:
				for v in value:
					pv2.append(from_json(v, TYPE_VECTOR2))
			return pv2
		TYPE_PACKED_VECTOR3_ARRAY:
			var pv3 := PackedVector3Array()
			if value is Array:
				for v in value:
					pv3.append(from_json(v, TYPE_VECTOR3))
			return pv3
		TYPE_PACKED_COLOR_ARRAY:
			var pc := PackedColorArray()
			if value is Array:
				for v in value:
					pc.append(from_json(v, TYPE_COLOR))
			return pc
		TYPE_NODE_PATH:
			return NodePath(str(value))
		TYPE_STRING_NAME:
			return StringName(str(value))
		TYPE_INT:
			return int(value)
		TYPE_FLOAT:
			return _float_from(value)
		TYPE_BOOL:
			return bool(value)
		TYPE_STRING:
			return str(value)
		_:
			return value


# Constructor prefix per composite type, so str_to_var only runs on plausible input.
const _CTOR_PREFIX := {
	TYPE_VECTOR2: "Vector2(",
	TYPE_VECTOR2I: "Vector2i(",
	TYPE_VECTOR3: "Vector3(",
	TYPE_VECTOR3I: "Vector3i(",
	TYPE_VECTOR4: "Vector4(",
	TYPE_VECTOR4I: "Vector4i(",
	TYPE_RECT2: "Rect2(",
	TYPE_RECT2I: "Rect2i(",
	TYPE_QUATERNION: "Quaternion(",
	TYPE_AABB: "AABB(",
	TYPE_PLANE: "Plane(",
	TYPE_BASIS: "Basis(",
	TYPE_TRANSFORM2D: "Transform2D(",
	TYPE_TRANSFORM3D: "Transform3D(",
	TYPE_PROJECTION: "Projection(",
}


## Parse a string form into a composite type, or null to fall back to dict/array.
static func _from_string(value: String, type: int) -> Variant:
	if _CTOR_PREFIX.has(type):
		# Cheap prefix check first: avoid calling str_to_var (and its parse-error
		# noise) on strings that clearly aren't the expected constructor form.
		if not value.strip_edges().begins_with(_CTOR_PREFIX[type]):
			return null
		var parsed: Variant = str_to_var(value)
		return parsed if typeof(parsed) == type else null
	if type == TYPE_COLOR:
		return Color.html(value) if value.is_valid_html_color() else null
	return null


## Coerce a JSON string into an Object-typed property value (issue #414).
## A "res://" path loads the resource (so set_node_property can assign
## materials/shaders/scripts); a null/missing value stays null (the honest
## "clear this property" case); anything else for TYPE_OBJECT is left for the
## caller to reject. Returns {ok, value} — ok=false means "not coercible".
static func object_from_json(value: Variant) -> Dictionary:
	if value == null:
		return {"ok": true, "value": null}
	if value is String:
		var path := str(value)
		if path.begins_with("res://") or path.begins_with("uid://"):
			if not ResourceLoader.exists(path):
				return {"ok": false, "error": "RESOURCE_NOT_FOUND", "hint": "No resource at '%s'." % path}
			var loaded: Resource = load(path)
			if loaded == null:
				return {"ok": false, "error": "RESOURCE_NOT_FOUND", "hint": "Could not load '%s'." % path}
			return {"ok": true, "value": loaded}
	return {"ok": false, "error": "VALIDATION_ERROR", "hint": "Object properties accept a res:// path or null; got %s." % _json_type_name(value)}


static func _json_type_name(value: Variant) -> String:
	match typeof(value):
		TYPE_STRING:
			return "a string"
		TYPE_INT:
			return "an int"
		TYPE_FLOAT:
			return "a float"
		TYPE_BOOL:
			return "a bool"
		TYPE_DICTIONARY:
			return "an object"
		TYPE_ARRAY:
			return "an array"
		_:
			return str(typeof(value))


## The Variant.Type *name* for a type id (e.g. 5 -> "Vector2") — the same token
## the JSON coercion layer (from_json) accepts shapes for (issue #533): an
## agent describing a class sees exactly the type names it can pass back.
static func variant_type_name(type_id: int) -> String:
	match type_id:
		TYPE_NIL: return "null"
		TYPE_BOOL: return "bool"
		TYPE_INT: return "int"
		TYPE_FLOAT: return "float"
		TYPE_STRING: return "String"
		TYPE_VECTOR2: return "Vector2"
		TYPE_VECTOR2I: return "Vector2I"
		TYPE_RECT2: return "Rect2"
		TYPE_RECT2I: return "Rect2I"
		TYPE_VECTOR3: return "Vector3"
		TYPE_VECTOR3I: return "Vector3I"
		TYPE_TRANSFORM2D: return "Transform2D"
		TYPE_VECTOR4: return "Vector4"
		TYPE_VECTOR4I: return "Vector4I"
		TYPE_PLANE: return "Plane"
		TYPE_QUATERNION: return "Quaternion"
		TYPE_AABB: return "AABB"
		TYPE_BASIS: return "Basis"
		TYPE_TRANSFORM3D: return "Transform3D"
		TYPE_PROJECTION: return "Projection"
		TYPE_COLOR: return "Color"
		TYPE_STRING_NAME: return "StringName"
		TYPE_NODE_PATH: return "NodePath"
		TYPE_RID: return "RID"
		TYPE_OBJECT: return "Object"
		TYPE_CALLABLE: return "Callable"
		TYPE_SIGNAL: return "Signal"
		TYPE_DICTIONARY: return "Dictionary"
		TYPE_ARRAY: return "Array"
		TYPE_PACKED_BYTE_ARRAY: return "PackedByteArray"
		TYPE_PACKED_INT32_ARRAY: return "PackedInt32Array"
		TYPE_PACKED_INT64_ARRAY: return "PackedInt64Array"
		TYPE_PACKED_FLOAT32_ARRAY: return "PackedFloat32Array"
		TYPE_PACKED_FLOAT64_ARRAY: return "PackedFloat64Array"
		TYPE_PACKED_STRING_ARRAY: return "PackedStringArray"
		TYPE_PACKED_VECTOR2_ARRAY: return "PackedVector2Array"
		TYPE_PACKED_VECTOR3_ARRAY: return "PackedVector3Array"
		TYPE_PACKED_COLOR_ARRAY: return "PackedColorArray"
		_: return "unknown(%d)" % type_id


static func _has_rect_keys(value: Variant) -> bool:
	return value is Dictionary and value.has("position") and value.has("size")


## Value equality for the post-set read-back check (#641): floats compare within
## ``epsilon`` (recursively through dict/array shapes); int/float are interchangeable
## for a numeric property; mismatched composite types differ. Used to fail a set
## whose coerced value did not actually land (instead of echoing the old value).
static func values_equal(a: Variant, b: Variant, epsilon: float = 1e-5) -> bool:
	var ta := typeof(a)
	var tb := typeof(b)
	if ta != tb:
		if (ta == TYPE_INT or ta == TYPE_FLOAT) and (tb == TYPE_INT or tb == TYPE_FLOAT):
			return absf(float(a) - float(b)) <= epsilon
		return false
	match ta:
		TYPE_FLOAT:
			return absf(a - b) <= epsilon or (is_nan(a) and is_nan(b))
		TYPE_DICTIONARY:
			var da := a as Dictionary
			var db := b as Dictionary
			if da.size() != db.size():
				return false
			for key in da:
				if not db.has(key) or not values_equal(da[key], db[key], epsilon):
					return false
			return true
		TYPE_ARRAY:
			var aa := a as Array
			var ab := b as Array
			if aa.size() != ab.size():
				return false
			for i in aa.size():
				if not values_equal(aa[i], ab[i], epsilon):
					return false
			return true
		_:
			return a == b


static func _has_xyz_keys(value: Variant) -> bool:
	return _has_cols(value, ["x", "y", "z"])


## True when ``value`` is a Dictionary carrying every key in ``keys``.
static func _has_cols(value: Variant, keys: Array) -> bool:
	if not (value is Dictionary):
		return false
	for key in keys:
		if not (value as Dictionary).has(key):
			return false
	return true


## Read a vector/color component from a dict ({"x": ...}) or array ([...]).
static func _component(value: Variant, key: String, index: int, default: float = 0.0) -> float:
	if value is Dictionary:
		return float(value.get(key, default))
	if value is Array and index < value.size():
		return float(value[index])
	return default
