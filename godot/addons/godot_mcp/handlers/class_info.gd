@tool
class_name MCPClassInfoHandlers
extends RefCounted
const Coerce := preload("../type_coerce.gd")
## Domain handler: ClassDB metadata for agent discovery (issue #533).
##
## Registered by the router on _init(). Read-only: answers "what can I set on
## any Tween?" / "which args does Vector3 take?" straight from ClassDB — no
## live node, no instantiation, no mutation. The property/method/signal `type`
## fields are Variant.Type *names*, the exact tokens the JSON coercion layer
## (type_coerce.gd from_json) accepts shapes for.

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_describe_class"] = _cmd_describe_class


## Describe an engine class from ClassDB: properties (+ defaults), methods
## (+ typed args / return), signals, constants, enums, the inheritance chain,
## and instantiability. `include_inherited` restricts every list to the class
## itself (no_inheritance=true); `include_private` keeps the _-prefixed
## entries Godot marks private.
func _cmd_describe_class(params: Dictionary) -> Dictionary:
	var wanted := str(params.get("class_name", ""))
	if wanted.is_empty():
		return _router._fail("VALIDATION_ERROR", "'class_name' must be a non-empty class name.")
	if not ClassDB.class_exists(wanted):
		# #533 honesty: point at the real classes (engine + script-defined)
		# instead of a bare refusal — script `class_name` globals are NOT in
		# ClassDB, so they must be suggested from ProjectSettings.
		var candidates: Array = []
		for c in ClassDB.get_class_list():
			candidates.append(str(c))
		for entry in ProjectSettings.get_global_class_list():
			candidates.append(str(entry.get("class", "")))
		var matches := _closest(wanted, candidates, 3)
		var hint := "Unknown class '%s'." % wanted
		if not matches.is_empty():
			hint += " Did you mean: %s?" % ", ".join(matches)
		else:
			hint += " List all classes with ClassDB.get_class_list() (script globals are separate)."
		return _router._fail("VALIDATION_ERROR", hint)

	var no_inheritance := not bool(params.get("include_inherited", false))
	var include_private := bool(params.get("include_private", false))

	var properties: Array = []
	for p in ClassDB.class_get_property_list(wanted, no_inheritance):
		var pname := str(p.get("name", ""))
		if not include_private and pname.begins_with("_"):
			continue
		properties.append({
			"name": pname,
			"type": Coerce.variant_type_name(int(p.get("type", 0))),
			"default": Coerce.to_json(ClassDB.class_get_property_default_value(wanted, pname)),
		})

	var methods: Array = []
	for m in ClassDB.class_get_method_list(wanted, no_inheritance):
		var mname := str(m.get("name", ""))
		if not include_private and mname.begins_with("_"):
			continue
		var args: Array = []
		for a in m.get("args", []):
			args.append({
				"name": str(a.get("name", "")),
				"type": Coerce.variant_type_name(int(a.get("type", 0))),
			})
		var ret: Dictionary = m.get("return", {})
		methods.append({
			"name": mname,
			"args": args,
			"return_type": Coerce.variant_type_name(int(ret.get("type", 0))),
		})

	var signals: Array = []
	for s in ClassDB.class_get_signal_list(wanted, no_inheritance):
		var sargs: Array = []
		for a in s.get("args", []):
			sargs.append({
				"name": str(a.get("name", "")),
				"type": Coerce.variant_type_name(int(a.get("type", 0))),
			})
		signals.append({"name": str(s.get("name", "")), "args": sargs})

	var constants: Array = []
	for c in ClassDB.class_get_integer_constant_list(wanted, no_inheritance):
		constants.append({
			"name": str(c),
			"value": ClassDB.class_get_integer_constant(wanted, c),
			"enum": str(ClassDB.class_get_integer_constant_enum(wanted, c, no_inheritance)),
		})

	var enums: Array = []
	for e in ClassDB.class_get_enum_list(wanted, no_inheritance):
		var members: Array = []
		for c in ClassDB.class_get_enum_constants(wanted, e, no_inheritance):
			members.append(str(c))
		enums.append({"name": str(e), "members": members})

	# The inheritance chain, root-first (Object ... class).
	var chain: Array = []
	var current := wanted
	while current != "" and current != "<anonymous>":
		chain.append(current)
		var parent := str(ClassDB.get_parent_class(current))
		if parent == current or parent.is_empty():
			break
		current = parent

	return _router._ok({
		"class_name": wanted,
		"inherits": str(ClassDB.get_parent_class(wanted)),
		"inherits_chain": chain,
		"can_instantiate": ClassDB.can_instantiate(wanted),
		"properties": properties,
		"methods": methods,
		"signals": signals,
		"constants": constants,
		"enums": enums,
	})


func _closest(given: String, candidates: Array, n: int) -> Array:
	# Small in-handler closest-match (difflib-equivalent is Python-side; the
	# addon gets a compact token-similarity pass so a typo returns real names).
	var scored: Array = []
	var given_lower := given.to_lower()
	for candidate in candidates:
		var c := str(candidate)
		if c.is_empty():
			continue
		var lower := c.to_lower()
		var score := 0.0
		if lower == given_lower:
			score = 1.0
		elif lower.begins_with(given_lower) and given_lower.length() >= 2:
			score = 0.9
		elif lower.contains(given_lower) and given_lower.length() >= 3:
			score = 0.7
		# Shared-prefix length ratio (cheap ordered similarity).
		var shared := 0
		for i in range(mini(given_lower.length(), lower.length())):
			if given_lower[i] == lower[i]:
				shared += 1
			else:
				break
		score = maxf(score, float(shared) / maxf(lower.length(), 1.0))
		if score > 0.0:
			scored.append({"c": c, "s": score})
	scored.sort_custom(func(a, b): return a["s"] > b["s"])
	var top: Array = []
	for entry in scored:
		top.append(str(entry["c"]))
		if top.size() >= n:
			break
	return top