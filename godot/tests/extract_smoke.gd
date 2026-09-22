extends SceneTree
## Headless smoke test for the extract-subtree helpers (issue #531).
##
## Run via: godot --headless --path godot/ --script res://tests/extract_scene_smoke.gd
## Exercises the pure pieces of cmd_extract_scene that don't need the editor:
## subtree counting, re-owning a duplicate for packing, and a real
## PackedScene.pack() + ResourceSaver.save() round-trip into a temp file. The
## editor glue (UndoRedo replace, EditorInterface calls, refusal hints) is
## covered by the cross-process e2e test.

const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	_test_count_subtree(failures)
	_test_reown_and_pack(failures)

	if failures.is_empty():
		print("EXTRACT_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("EXTRACT_TEST_FAIL")
		quit(1)


func _eq(failures: Array[String], label: String, got: Variant, want: Variant) -> void:
	if typeof(got) != typeof(want) or got != want:
		failures.append("%s: expected %s, got %s" % [label, str(want), str(got)])


func _test_count_subtree(failures: Array[String]) -> void:
	# Mirror of the handler's _count_subtree: the root counts as one.
	var root := Node2D.new()
	root.name = "Gun"
	var barrel := Node2D.new()
	barrel.name = "Barrel"
	var tip := Node2D.new()
	tip.name = "Tip"
	root.add_child(barrel)
	barrel.add_child(tip)
	var count := 1
	for child in root.get_children():
		count += _count(child)
	_eq(failures, "count", count, 3)
	_eq(failures, "count.leaf", _count(tip), 1)
	root.free()


func _count(node: Node) -> int:
	var count := 1
	for child in node.get_children():
		count += _count(child)
	return count


func _test_reown_and_pack(failures: Array[String]) -> void:
	# A duplicate's nodes have null owners; pack() only serializes nodes owned by
	# the pack root — so the handler re-owns the whole duplicated subtree first.
	var root := Node2D.new()
	root.name = "Gun"
	var barrel := Node2D.new()
	barrel.name = "Barrel"
	barrel.position = Vector2(3, 4)
	root.add_child(barrel)
	var duplicate := root.duplicate()
	_eq(failures, "dup.owner_null", (duplicate.get_child(0) as Node).owner == null, true)
	_reown(duplicate, duplicate)
	_eq(failures, "dup.reowned", (duplicate.get_child(0) as Node).owner == duplicate, true)
	var packed := PackedScene.new()
	_eq(failures, "pack.ok", packed.pack(duplicate), OK)
	duplicate.free()
	# Round-trip: instantiate the packed scene and check the shape + a property.
	# Node.name round-trips as StringName through pack/instantiate, so compare
	# as strings (typeof differs: String vs StringName).
	var instance := packed.instantiate()
	_eq(failures, "rt.root_name", str(instance.name), "Gun")
	_eq(failures, "rt.child_count", instance.get_children().size(), 1)
	var rt_barrel := instance.get_child(0) as Node2D
	_eq(failures, "rt.barrel_name", str(rt_barrel.name), "Barrel")
	_eq(failures, "rt.barrel_pos", Coerce.to_json(rt_barrel.position), {"x": 3.0, "y": 4.0})
	# Save to a temp file and reload it — the full ResourceSaver path.
	var path := "res://tmp_extract_smoke.tscn"
	_eq(failures, "save.ok", ResourceSaver.save(packed, path), OK)
	_eq(failures, "save.exists", FileAccess.file_exists(path), true)
	var reloaded: PackedScene = load(path)
	_eq(failures, "reload.ok", reloaded != null, true)
	var reloaded_instance := reloaded.instantiate()
	_eq(failures, "reload.root", str(reloaded_instance.name), "Gun")
	reloaded_instance.free()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	instance.free()
	root.free()


func _reown(node: Node, new_root: Node) -> void:
	node.owner = new_root
	for child in node.get_children():
		_reown(child, new_root)