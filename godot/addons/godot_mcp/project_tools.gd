@tool
class_name MCPProjectTools
extends RefCounted
## Project-registered tools: discovery + execution (#761).
##
## A project tool is a `func` in an `@tool` script directly preceded by a
## `## @mcp_tool` doc tag, e.g.
##
##     @tool
##     extends RefCounted
##
##     ## Spawn a wave of enemies.
##     ## @mcp_tool safety=mutating
##     func spawn_wave(count: int, kind: String = "enemy") -> Dictionary:
##         return {"spawned": count}
##
## The scanner reads the *source* (doc comments are not available through
## GDScript reflection), derives a JSON Schema from the static types, and rejects
## anything it cannot describe precisely. Execution is `load(script).new()` +
## `callv`, so project tool scripts should extend `RefCounted`.

const Coerce := preload("./type_coerce.gd")

const TAG := "@mcp_tool"
const SAFETY_CLASSES := ["read_only", "mutating", "destructive"]
## Project tools belong to the project, not the addon's own dependencies.
const SKIP_DIRS := ["res://addons", "res://.godot"]


## Scan `root` for annotated functions. Returns `{tools: [...], rejected: [...]}`.
static func scan(root: String = "res://") -> Dictionary:
	var files: Array[String] = []
	_collect(root, files)
	files.sort()
	var tools: Array = []
	var rejected: Array = []
	for path in files:
		_scan_file(path, tools, rejected)
	return {"tools": tools, "rejected": rejected}


## Call one annotated function with named arguments. Returns `{result: <json>}`
## or `{error, hint}` — never a raw script error.
static func run(script_path: String, function_name: String, args: Dictionary) -> Dictionary:
	var script: Script = load(script_path)
	if script == null:
		return {"error": "RESOURCE_NOT_FOUND", "hint": "No script at '%s'." % script_path}
	var method := _find_method(script, function_name)
	if method.is_empty():
		return {
			"error": "RESOURCE_NOT_FOUND",
			"hint": "No function '%s' in %s." % [function_name, script_path],
		}
	var instance: Object = script.new()
	if instance == null:
		return {
			"error": "UNSUPPORTED",
			"hint": "Cannot instantiate %s; project tool scripts should extend RefCounted." % script_path,
		}
	var constants: Dictionary = script.get_script_constant_map()
	var positional: Array = []
	for meta in method.get("args", []):
		var param_name := str(meta.get("name", ""))
		if not args.has(param_name):
			break  # optional trailing parameters are simply omitted
		positional.append(_coerce_arg(args[param_name], int(meta.get("type", TYPE_NIL)), constants))
	var result: Variant = instance.callv(function_name, positional)
	var payload: Variant = Coerce.to_json(result)
	if instance is Node:
		(instance as Node).free()
	return {"result": payload}


# -- discovery ---------------------------------------------------------------

static func _collect(dir_path: String, out: Array[String]) -> void:
	var dir := DirAccess.open(dir_path)
	if dir == null:
		return
	dir.list_dir_begin()
	var entry := dir.get_next()
	while entry != "":
		if entry.begins_with("."):
			entry = dir.get_next()
			continue
		var full := dir_path.path_join(entry)
		if dir.current_is_dir():
			if not SKIP_DIRS.has(full):
				_collect(full, out)
		elif entry.ends_with(".gd"):
			out.append(full)
		entry = dir.get_next()
	dir.list_dir_end()


static func _scan_file(path: String, tools: Array, rejected: Array) -> void:
	var text := FileAccess.get_file_as_string(path)
	if text.is_empty() or not text.contains(TAG):
		return
	var lines := text.split("\n")
	var enums := _parse_enums(lines)
	var doc: Array[String] = []
	var pending := false
	var safety := ""
	for i in lines.size():
		var stripped := lines[i].strip_edges()
		if stripped.begins_with("##"):
			var body := stripped.substr(2).strip_edges()
			if body.begins_with(TAG):
				pending = true
				safety = _tag_safety(body)
			else:
				doc.append(body)
			continue
		if stripped.begins_with("@"):
			continue  # @tool / @warning_ignore between the doc block and func
		if stripped.begins_with("func "):
			if pending:
				_parse_func(path, stripped, i + 1, doc, safety, enums, tools, rejected)
			pending = false
			doc = []
			continue
		# Any other line ends the doc block; a blank line detaches a pending tag.
		doc = []
		pending = false


static func _parse_func(
	path: String,
	line: String,
	line_no: int,
	doc: Array[String],
	safety: String,
	enums: Dictionary,
	tools: Array,
	rejected: Array
) -> void:
	var rest := line.substr(5)
	var paren := rest.find("(")
	var close := rest.rfind(")")
	if paren <= 0 or close < paren:
		rejected.append(_reject(path, "", line_no, "could not parse the function signature"))
		return
	var function_name := rest.substr(0, paren).strip_edges()
	var properties := {}
	var required: Array[String] = []
	var saw_default := false
	for raw in _split_top(rest.substr(paren + 1, close - paren - 1)):
		var arg := raw.strip_edges()
		if arg.is_empty():
			continue
		var default_text := ""
		var eq := _top_level_find(arg, "=")
		if eq >= 0:
			default_text = arg.substr(eq + 1).strip_edges()
			arg = arg.substr(0, eq).strip_edges()
			saw_default = true
		var colon := arg.find(":")
		var arg_name := arg if colon < 0 else arg.substr(0, colon).strip_edges()
		if colon < 0:
			rejected.append(
				_reject(path, function_name, line_no, "untyped parameter '%s'" % arg_name)
			)
			return
		if saw_default and default_text.is_empty():
			rejected.append(
				_reject(
					path,
					function_name,
					line_no,
					"non-default parameter '%s' follows a default parameter" % arg_name
				)
			)
			return
		var schema := _schema_for(arg.substr(colon + 1).strip_edges(), enums)
		if schema.is_empty():
			rejected.append(
				_reject(
					path,
					function_name,
					line_no,
					"unsupported type '%s' for parameter '%s'"
					% [arg.substr(colon + 1).strip_edges(), arg_name]
				)
			)
			return
		if default_text.is_empty():
			required.append(arg_name)
		else:
			var parsed := _default_value(schema.get("type", ""), default_text)
			if parsed != null:
				schema["default"] = parsed
		properties[arg_name] = schema

	var safety_value := "mutating" if safety.is_empty() else safety
	if not SAFETY_CLASSES.has(safety_value):
		rejected.append(
			_reject(path, function_name, line_no, "unknown safety class '%s'" % safety_value)
		)
		return
	tools.append(
		{
			"name": function_name,
			"script": path,
			"function": function_name,
			"description": _describe(doc),
			"safety_class": safety_value,
			"parameters": {
				"type": "object",
				"properties": properties,
				"required": required,
				"additionalProperties": false,
			},
		}
	)


# -- parsing helpers ---------------------------------------------------------

static func _reject(path: String, function_name: String, line_no: int, reason: String) -> Dictionary:
	return {
		"script": path,
		"function": function_name if not function_name.is_empty() else null,
		"reason": reason,
		"line": line_no,
	}


static func _tag_safety(body: String) -> String:
	for token in body.substr(TAG.length()).strip_edges().split(" ", false):
		if token.begins_with("safety="):
			return token.trim_prefix("safety=").strip_edges()
	return ""


static func _describe(doc: Array[String]) -> String:
	var parts: Array[String] = []
	for line in doc:
		if not line.is_empty():
			parts.append(line)
	return " ".join(parts)


static func _parse_enums(lines: PackedStringArray) -> Dictionary:
	var out := {}
	for raw in lines:
		var line := raw.strip_edges()
		if not line.begins_with("enum "):
			continue
		var brace := line.find("{")
		var close := line.rfind("}")
		if brace < 0 or close < brace:
			continue
		var enum_name := line.substr(5, brace - 5).strip_edges().trim_suffix(":")
		if enum_name.is_empty():
			continue
		var values: Array = []
		for part in line.substr(brace + 1, close - brace - 1).split(","):
			var value := part.strip_edges()
			if value.is_empty():
				continue
			var eq := _top_level_find(value, "=")
			if eq >= 0:
				value = value.substr(0, eq).strip_edges()
			values.append(value)
		out[enum_name] = values
	return out


## Split on commas that are not inside `()[]{}` or a quoted string.
static func _split_top(text: String) -> PackedStringArray:
	var parts := PackedStringArray()
	var depth := 0
	var quote := ""
	var start := 0
	for i in text.length():
		var ch := text[i]
		if quote != "":
			if ch == quote:
				quote = ""
			continue
		if ch == '"' or ch == "'":
			quote = ch
		elif ch == "(" or ch == "[" or ch == "{":
			depth += 1
		elif ch == ")" or ch == "]" or ch == "}":
			depth -= 1
		elif ch == "," and depth == 0:
			parts.append(text.substr(start, i - start))
			start = i + 1
	parts.append(text.substr(start))
	return parts


static func _top_level_find(text: String, needle: String) -> int:
	var depth := 0
	var quote := ""
	for i in text.length():
		var ch := text[i]
		if quote != "":
			if ch == quote:
				quote = ""
			continue
		if ch == '"' or ch == "'":
			quote = ch
		elif ch == "(" or ch == "[" or ch == "{":
			depth += 1
		elif ch == ")" or ch == "]" or ch == "}":
			depth -= 1
		elif depth == 0 and ch == needle:
			return i
	return -1


static func _schema_for(type_text: String, enums: Dictionary) -> Dictionary:
	match type_text:
		"int":
			return {"type": "integer"}
		"float":
			return {"type": "number"}
		"bool":
			return {"type": "boolean"}
		"String", "StringName", "NodePath":
			return {"type": "string"}
		"Vector2":
			return _object_schema(["x", "y"])
		"Vector3":
			return _object_schema(["x", "y", "z"])
		"Color":
			return _object_schema(["r", "g", "b", "a"])
	if enums.has(type_text):
		return {"type": "string", "enum": enums[type_text]}
	if type_text.begins_with("Array[") and type_text.ends_with("]"):
		var inner := _schema_for(type_text.substr(6, type_text.length() - 7).strip_edges(), enums)
		if inner.is_empty():
			return {}
		return {"type": "array", "items": inner}
	return {}


static func _object_schema(keys: Array) -> Dictionary:
	var properties := {}
	for key in keys:
		properties[key] = {"type": "number"}
	return {
		"type": "object",
		"properties": properties,
		"required": keys,
		"additionalProperties": false,
	}


static func _default_value(schema_type: String, text: String) -> Variant:
	if text.is_empty():
		return null
	if schema_type == "boolean":
		return text == "true"
	if schema_type == "integer" and text.is_valid_int():
		return int(text)
	if schema_type == "number" and text.is_valid_float():
		return float(text)
	if schema_type == "string":
		var trimmed := text.strip_edges()
		if trimmed.length() >= 2 and trimmed.begins_with('"') and trimmed.ends_with('"'):
			return trimmed.substr(1, trimmed.length() - 2)
	return null


# -- execution helpers -------------------------------------------------------

static func _find_method(script: Script, function_name: String) -> Dictionary:
	for method in script.get_script_method_list():
		if str(method.get("name", "")) == function_name:
			return method
	return {}


## Convert a JSON argument to what the function expects (enum strings → ints,
## math-type objects → Vector2/3/Color).
static func _coerce_arg(value: Variant, type_id: int, constants: Dictionary) -> Variant:
	if typeof(value) == TYPE_STRING and type_id == TYPE_INT:
		for key in constants:
			var constant: Variant = constants[key]
			if constant is Dictionary and (constant as Dictionary).has(value):
				return (constant as Dictionary)[value]
	if typeof(value) == TYPE_DICTIONARY and type_id in [TYPE_VECTOR2, TYPE_VECTOR3, TYPE_COLOR]:
		return Coerce.from_json(value, type_id)
	return value
