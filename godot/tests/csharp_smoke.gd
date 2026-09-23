@tool
extends SceneTree
## Headless behavior test for language-aware script authoring (issue #207 Phase 1).
##
## Run via: godot --headless --path godot/ --script res://tests/csharp_smoke.gd
## Verifies the pure pieces: the csproj probe (none in this project) and the
## backend capability fields riding cmd_get_project_info via the router (a
## non-.NET build reports csharp_supported=false — the honest negative, which is
## itself the contract for agents branching before authoring .cs). The .cs
## read/write/list paths are covered by contract tests + the parse-refusal tests.
## Prints CSHARP_TEST_OK, quits 0 on success.

const Router := preload("res://addons/godot_mcp/command_router.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	_test_backend_probe(failures)

	if failures.is_empty():
		print("CSHARP_TEST_OK")
		quit(0)
	else:
		push_error("CSHARP_TEST_FAILURES: %s" % [str(failures)])
		quit(1)


func _eq(failures: Array[String], what: String, got: Variant, expected: Variant) -> void:
	if got != expected:
		failures.append("%s: expected %s, got %s" % [what, str(expected), str(got)])


func _test_backend_probe(failures: Array[String]) -> void:
	# This godot/ test project is NOT a .NET build: CSharpScript is absent and
	# there is no .csproj — both probe fields must honestly report false.
	var router: Object = Router.new()
	var result: Dictionary = router.handle({"id": "1", "command": "cmd_get_project_info", "params": {}})
	_eq(failures, "info.ok", result.get("ok"), true)
	var info: Dictionary = result.get("result", {})
	_eq(failures, "info.csharp_supported", info.get("csharp_supported"), false)
	_eq(failures, "info.csharp_project", info.get("csharp_project"), false)
	# The language-aware list: no .cs files in this project, .gd files exist.
	var cs_list: Dictionary = router.handle({"id": "2", "command": "cmd_list_scripts", "params": {"language": "cs"}})
	_eq(failures, "list.cs.ok", cs_list_result(cs_list).get("ok"), true)
	_eq(failures, "list.cs.empty", (cs_list_result(cs_list).get("result", {}).get("scripts", []) as Array).size(), 0)
	var bad: Dictionary = router.handle({"id": "3", "command": "cmd_list_scripts", "params": {"language": "py"}})
	_eq(failures, "list.bad_language_refused", bad.get("ok"), false)
	router.dispose()


## The typed router result carries the body under "result" (the _ok shape).
func cs_list_result(cs_list: Dictionary) -> Dictionary:
	return cs_list