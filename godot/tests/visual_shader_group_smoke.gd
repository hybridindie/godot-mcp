@tool
extends SceneTree
## Headless behavior test for VisualShader node groups/subgraphs (issue #601).
##
## Run via: godot --headless --path godot/ --script res://tests/visual_shader_group_smoke.gd
## On 4.4–4.7 the group verbs are inert: every command returns a structured
## UNSUPPORTED envelope (the gate is ClassDB.class_exists("VisualShaderGroup"),
## so this script itself still parses on the older editor). On 4.8+ it builds a
## real group + member headlessly and checks the read helper reports membership.
## Prints VISUAL_SHADER_GROUP_TEST_OK, quits 0 on success.

const Router := preload("res://addons/godot_mcp/command_router.gd")
const VisualShaderRead := preload("res://addons/godot_mcp/visual_shader_read.gd")

const GROUP_COMMANDS := [
	{
		"command": "cmd_create_shader_group",
		"params": {"shader_path": "", "name": "fx", "node_id": 2},
	},
	{
		"command": "cmd_rename_shader_group",
		"params": {"shader_path": "", "node_id": 2, "name": "glow"},
	},
	{
		"command": "cmd_remove_shader_group",
		"params": {"shader_path": "", "node_id": 2, "confirm": true},
	},
	{
		"command": "cmd_add_shader_group_node",
		"params": {
			"shader_path": "",
			"group_node_id": 2,
			"node_type": "VisualShaderNodeFloatConstant",
			"node_id": 0,
		},
	},
	{
		"command": "cmd_remove_shader_group_node",
		"params": {"shader_path": "", "group_node_id": 2, "node_id": 0, "confirm": true},
	},
]


func _initialize() -> void:
	var failures: Array[String] = []
	var supported := ClassDB.class_exists("VisualShaderGroup")
	var router := Router.new()

	for entry in GROUP_COMMANDS:
		var body: Dictionary = router.handle({
			"id": "group",
			"command": entry["command"],
			"params": entry["params"],
		})
		if supported:
			# The gate is bypassed; an empty shader_path is a validation error,
			# never UNSUPPORTED.
			if str(body.get("error", "")) == "UNSUPPORTED":
				failures.append("%s: unexpectedly UNSUPPORTED on this editor" % entry["command"])
		elif body.get("ok") != false or str(body.get("error", "")) != "UNSUPPORTED":
			failures.append(
				"%s: expected UNSUPPORTED on Godot %s, got %s"
				% [entry["command"], str(Engine.get_version_info().get("string", "")), str(body)]
			)
		elif not str(body.get("hint", "")).contains("4.8"):
			failures.append("%s: UNSUPPORTED hint should name 4.8: %s" % [entry["command"], str(body)])

	if supported:
		_check_supported_path(failures)
	else:
		# The read helper must still serialize a normal shader, with no groups.
		var plain := VisualShader.new()
		var data: Dictionary = VisualShaderRead.serialize(plain)
		if data.get("groups") != []:
			failures.append("read: expected groups [] on a group-less shader, got %s" % str(data.get("groups")))

	router = null

	if failures.is_empty():
		print("VISUAL_SHADER_GROUP_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("VISUAL_SHADER_GROUP_TEST_FAIL")
		quit(1)


## 4.8+ only: build a group with one member directly (no editor needed) and check
## the pure read helper reports the membership.
func _check_supported_path(failures: Array[String]) -> void:
	var shader := VisualShader.new()
	var type := int(shader.get_mode())

	var group: Resource = ClassDB.instantiate("VisualShaderGroup")
	group.call("set_group_name", "fx")
	var group_node: VisualShaderNode = ClassDB.instantiate("VisualShaderNodeGroup")
	group_node.call("set_group", group)
	shader.add_node(type, group_node, Vector2(10, 20), 2)

	var member := VisualShaderNodeFloatConstant.new()
	group.call("add_node", member, Vector2(5, 6), 0)

	var data: Dictionary = VisualShaderRead.serialize(shader)
	var groups: Array = data.get("groups", [])
	if groups.size() != 1:
		failures.append("read: expected 1 group, got %s" % str(groups))
		return
	var group_info: Dictionary = groups[0]
	_eq(failures, "group.node_id", group_info.get("node_id"), 2)
	_eq(failures, "group.name", group_info.get("name"), "fx")
	var members: Array = group_info.get("members", [])
	if members.size() != 1:
		failures.append("read: expected 1 member, got %s" % str(members))
		return
	_eq(failures, "member.id", members[0].get("id"), 0)
	_eq(failures, "member.type", members[0].get("type"), "VisualShaderNodeFloatConstant")
	_eq(failures, "member.group", members[0].get("group"), 2)


func _eq(failures: Array[String], label: String, got: Variant, want: Variant) -> void:
	if typeof(got) != typeof(want) or got != want:
		failures.append("%s: expected %s, got %s" % [label, str(want), str(got)])
