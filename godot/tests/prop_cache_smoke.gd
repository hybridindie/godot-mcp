@tool
extends SceneTree
## Headless behavior test for the property-type cache liveness guard (issue #540).
##
## Run via: godot --headless --path godot/ --script res://tests/prop_cache_smoke.gd
## Pins the two fixes #540 requires:
## 1. A freed object's cache entry cannot be served to a new object reusing its
##    instance id: the cache stores a WeakRef per entry and the read guard
##    refreshes when the cached object is not the one being read. Godot reuses
##    ids after free, but a collision can't be forced deterministically — so the
##    reuse case is simulated by transplanting the dead entry onto a live
##    object's id (exactly what a reused id looks like to the cache).
## 2. invalidate_prop_cache erases the entry (the delete-path API #540 wires
##    into cmd_delete_node).
## Prints PROP_CACHE_TEST_OK, quits 0 on success.

const Helpers := preload("res://addons/godot_mcp/mcp_helpers.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	var helpers := Helpers.new()

	# === 1. Live reads cache normally (the hit path stays a hit) ===
	var a := Node3D.new()
	var t1: int = helpers.property_type(a, "position")
	if t1 != TYPE_VECTOR3:
		failures.append("expected Node3D.position to be TYPE_VECTOR3, got %d" % t1)
	var t2: int = helpers.property_type(a, "position")
	if t2 != TYPE_VECTOR3:
		failures.append("second read (cache hit) returned a different type: %d" % t2)
	var a_id: int = a.get_instance_id()

	# === 2. Simulated id reuse: the freed object's entry must not be served ===
	var stale: Dictionary = helpers._prop_cache.get(a_id, {}) as Dictionary
	if stale.is_empty():
		failures.append("setup: cache did not populate for the first object")
	a.free()
	var b := Node2D.new()
	# Transplant the dead entry onto b's id — exactly what an id collision serves.
	helpers._prop_cache[b.get_instance_id()] = stale
	var poisoned: int = helpers.property_type(b, "position")
	if poisoned != TYPE_VECTOR2:
		failures.append(
			"id reuse served a stale entry: expected TYPE_VECTOR2 for Node2D.position, got %d" % poisoned
		)
	# The refreshed entry must now belong to b (live weakref), not the dead one.
	var b_entry: Dictionary = helpers._prop_cache.get(b.get_instance_id(), {}) as Dictionary
	var b_ref: Variant = b_entry.get("obj")
	if not (b_ref is WeakRef and (b_ref as WeakRef).get_ref() == b):
		failures.append("refresh did not rebind the entry to the live object")
	# And the hit path works again on the rebound entry.
	if helpers.property_type(b, "position") != TYPE_VECTOR2:
		failures.append("rebound entry did not serve the hit path")
	b.free()

	# === 3. invalidate_prop_cache erases the entry (the delete-path API) ===
	var e := Node3D.new()
	helpers.property_type(e, "position")
	var e_id: int = e.get_instance_id()
	if not helpers._prop_cache.has(e_id):
		failures.append("setup: property_type did not populate the cache")
	helpers.invalidate_prop_cache(e)
	if helpers._prop_cache.has(e_id):
		failures.append("invalidate_prop_cache left the entry in place")
	e.free()

	helpers = null

	if failures.is_empty():
		print("PROP_CACHE_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("PROP_CACHE_TEST_FAIL")
		quit(1)