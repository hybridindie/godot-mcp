extends SceneTree
## Headless smoke test for the project file mover (issue #532).
##
## Run via: godot --headless --path godot/ --script res://tests/move_file_smoke.gd
## Exercises the pure remap helpers (MCPFsRemap — the scene_inspect.gd pattern:
## paths in, JSON-safe out, no editor access): text-kind detection, res://
## containment, dependency discovery, path-form remap with counts, and the real
## DirAccess move round-trip. The EditorInterface glue (unsaved-scene refusal,
## filesystem scan, ResourceUID re-point) is covered by the e2e test.

const Remap := preload("res://addons/godot_mcp/mcp_fs_remap.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	_test_text_detection(failures)
	_test_containment(failures)
	_test_move_with_remap(failures)

	if failures.is_empty():
		print("MOVE_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("MOVE_TEST_FAIL")
		quit(1)


func _eq(failures: Array[String], label: String, got: Variant, want: Variant) -> void:
	if typeof(got) != typeof(want) or got != want:
		failures.append("%s: expected %s, got %s" % [label, str(want), str(got)])


func _test_text_detection(failures: Array[String]) -> void:
	_eq(failures, "text.gd", Remap.is_text_resource("res://a/b.gd"), true)
	_eq(failures, "text.tscn", Remap.is_text_resource("res://a.tscn"), true)
	_eq(failures, "text.tres", Remap.is_text_resource("res://a.tres"), true)
	_eq(failures, "text.import", Remap.is_text_resource("res://a.png.import"), true)
	_eq(failures, "text.cfg", Remap.is_text_resource("res://project.cfg"), true)
	_eq(failures, "text.cs", Remap.is_text_resource("res://a.cs"), true)
	_eq(failures, "binary.wav", Remap.is_text_resource("res://a.wav"), false)
	_eq(failures, "binary.png", Remap.is_text_resource("res://a.png"), false)


func _test_containment(failures: Array[String]) -> void:
	# Mirrors the server-side posixpath check: .. climbs escape, / is absolute.
	_eq(failures, "ct.stays", Remap.escapes_res_root("res://a/../b.gd"), false)
	_eq(failures, "ct.climbs", Remap.escapes_res_root("res://../outside.gd"), true)
	_eq(failures, "ct.abs", Remap.escapes_res_root("res:///etc/passwd"), true)
	_eq(failures, "ct.non_res", Remap.escapes_res_root("user://a.gd"), true)
	_eq(failures, "ct.plain", Remap.escapes_res_root("res://a.gd"), false)


func _test_move_with_remap(failures: Array[String]) -> void:
	# Build a real file pair in a scratch subdir (the smoke test's own source
	# lives under res://tests and would otherwise match its own path string —
	# the discovery walk is project-wide, so both the dir and the scene text
	# are assembled at runtime from literals the test file does not contain).
	var dir := "res://tmp_mv_" + "dir"
	DirAccess.make_dir_recursive_absolute(dir)
	var script_path := dir + "/old.gd"
	var scene_path := dir + "/ref.tscn"
	var new_script_path := dir + "/new.gd"
	var write := func(p: String, text: String) -> void:
		var f := FileAccess.open(p, FileAccess.WRITE)
		f.store_string(text)
		f.close()
	write.call(script_path, "@tool\nextends Node\nvar x := 1\n")
	var scene_text := "[gd_scene load_steps=2 format=3]\n\n[ext_resource type=\"Script\" path=\""
	scene_text += script_path + "\" id=\"1\"]\n\n[node name=\"A\" type=\"Node\"]\nscript = ExtResource(\"1\")\n"
	write.call(scene_path, scene_text)

	var refs: Array = Remap.find_referencing_files(script_path, "")
	var found := false
	for f: String in refs:
		if f == scene_path:
			found = true
	_eq(failures, "refs.find_scene", found, true)
	# The mover itself must not be counted as a referencing file.
	for f: String in refs:
		_eq(failures, "refs.not_self", f == script_path, false)

	# Remap: only the referencing file changes, with a counted rewrite.
	var writes: Array = []
	var writer := func(p: String, text: String) -> void:
		writes.append(p)
		var file := FileAccess.open(p, FileAccess.WRITE)
		file.store_string(text)
		file.close()
	var updated: Array = Remap.rewrite_references(script_path, new_script_path, refs, writer)
	_eq(failures, "remap.count_files", updated.size(), 1)
	_eq(failures, "remap.file", updated[0]["file"], scene_path)
	_eq(failures, "remap.count", updated[0]["count"], 1)
	_eq(failures, "remap.rewritten", FileAccess.get_file_as_string(scene_path).contains(new_script_path), true)
	_eq(failures, "remap.old_gone", FileAccess.get_file_as_string(scene_path).contains(script_path), false)

	# Idempotence: a second remap finds nothing to change.
	var second: Array = Remap.rewrite_references(script_path, new_script_path, refs, writer)
	_eq(failures, "remap.idempotent", second.size(), 0)

	# Real DirAccess move of the file: the rename itself round-trips.
	write.call(new_script_path, "@tool\nextends Node\nvar x := 1\n")
	_eq(failures, "move.ok", DirAccess.rename_absolute(
		ProjectSettings.globalize_path(new_script_path),
		ProjectSettings.globalize_path(script_path),
	), OK)
	_eq(failures, "move.landed", FileAccess.file_exists(script_path), true)
	_eq(failures, "move.old_gone", FileAccess.file_exists(new_script_path), false)

	DirAccess.remove_absolute(ProjectSettings.globalize_path(script_path))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(scene_path))
	DirAccess.remove_absolute("res://tmp_mv_dir")