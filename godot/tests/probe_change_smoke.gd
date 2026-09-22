extends SceneTree
## Headless probe smoke test for push-on-change sampling (issue #536).
##
## Run via: godot --headless --path godot/ --script res://tests/probe_change_smoke.gd
## Exercises the probe's change-test logic in isolation (the dedup branch of the
## _process sample loop lives in _should_queue, so it is verifiable without a
## live debugger session): consecutive identical values collapse, epsilon
## tolerates float noise inside nested shapes, and legacy mode never drops.

const Probe := preload("res://addons/godot_mcp/mcp_runtime_probe.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	_test_change_test(failures)
	_test_dedup_loop(failures)

	if failures.is_empty():
		print("PROBE_CHANGE_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("PROBE_CHANGE_TEST_FAIL")
		quit(1)


func _eq(failures: Array[String], label: String, got: Variant, want: Variant) -> void:
	if typeof(got) != typeof(want) or got != want:
		failures.append("%s: expected %s, got %s" % [label, str(want), str(got)])


func _test_change_test(failures: Array[String]) -> void:
	var probe := Probe.new()
	# Exact for non-floats; null vs 0 are different.
	_eq(failures, "ct.null_eq", probe._values_equal(null, null, 0.0001), true)
	_eq(failures, "ct.null_vs_zero", probe._values_equal(null, 0, 0.0001), false)
	_eq(failures, "ct.int_eq", probe._values_equal(5, 5, 0.0), true)
	_eq(failures, "ct.int_ne", probe._values_equal(5, 6, 0.0), false)
	_eq(failures, "ct.str_eq", probe._values_equal("a", "a", 0.0), true)
	# Floats compare within epsilon.
	_eq(failures, "ct.float_within", probe._values_equal(1.00001, 1.00002, 0.0001), true)
	_eq(failures, "ct.float_beyond", probe._values_equal(1.0, 1.001, 0.0001), false)
	_eq(failures, "ct.float_exact", probe._values_equal(1.0, 1.0, 0.0), true)
	# Nested shapes (what _json_safe emits): any component beyond epsilon differs.
	var v2a := {"x": 1.0, "y": 2.0}
	var v2b := {"x": 1.0, "y": 2.00005}
	_eq(failures, "ct.vec2_within", probe._values_equal(v2a, v2b, 0.0001), true)
	var v2c := {"x": 1.0, "y": 2.001}
	_eq(failures, "ct.vec2_beyond", probe._values_equal(v2a, v2c, 0.0001), false)
	# Shape mismatch is a difference.
	_eq(failures, "ct.dict_size", probe._values_equal({"x": 1.0}, {"x": 1.0, "y": 1.0}, 0.0001), false)
	_eq(failures, "ct.dict_key", probe._values_equal({"x": 1.0}, {"z": 1.0}, 0.0001), false)
	_eq(failures, "ct.arr_len", probe._values_equal([1, 2], [1], 0.0001), false)
	_eq(failures, "ct.arr_elem", probe._values_equal([1.0, 2.0], [1.0, 2.5], 0.0001), false)
	_eq(failures, "ct.type_mismatch", probe._values_equal(1, "1", 0.0), false)
	probe.free()


func _test_dedup_loop(failures: Array[String]) -> void:
	# Drive the dedup branch through _should_queue_sample: a static value queues
	# once then collapses; a changing value queues every frame; legacy mode
	# queues everything; stats stay honest.
	var probe := Probe.new()
	probe._monitor_on_change_only = true
	probe._monitor_epsilon = 0.0001
	probe._monitor_last_value = null
	probe._monitor_last_queued_frame = -1

	# Frame 1: first sample always queues (last_value null).
	_eq(failures, "dq.first", probe._should_queue_sample(100, 1), true)
	_eq(failures, "dq.last_stored", probe._monitor_last_value, 100)
	_eq(failures, "dq.last_frame", probe._monitor_last_queued_frame, 1)
	# Frame 2: same value → dropped.
	_eq(failures, "dq.same_dropped", probe._should_queue_sample(100, 2), false)
	# Frame 3: value changes → queued.
	_eq(failures, "dq.changed", probe._should_queue_sample(200, 3), true)
	# Frame 4: back to the first value → queued (it differs from the last).
	_eq(failures, "dq.changed_back", probe._should_queue_sample(100, 4), true)

	# Epsilon-tolerant float: within epsilon counts as unchanged.
	probe._monitor_last_value = 5.0
	probe._monitor_last_queued_frame = 10
	_eq(failures, "dq.float_within", probe._should_queue_sample(5.00005, 11), false)
	_eq(failures, "dq.float_beyond", probe._should_queue_sample(5.1, 12), true)

	# Legacy mode (on_change_only=false) queues every sample.
	probe._monitor_on_change_only = false
	probe._monitor_last_value = 100
	_eq(failures, "dq.legacy_same", probe._should_queue_sample(100, 13), true)

	# Honest counters: reset + run a mixed series.
	probe._monitor_on_change_only = true
	probe._monitor_epsilon = 0.0001
	probe._monitor_last_value = null
	probe._monitor_last_queued_frame = -1
	probe._monitor_dropped_duplicates = 0
	probe._monitor_sampling_usec = 0
	var series := [7, 7, 7, 8, 8, 9]
	for i in range(series.size()):
		if probe._should_queue_sample(series[i], i + 1):
			probe._monitor_samples.append({"frame": i + 1, "value": series[i]})
	_eq(failures, "dq.series_len", probe._monitor_samples.size(), 3)
	_eq(failures, "dq.series_dropped", probe._monitor_dropped_duplicates, 3)
	_eq(failures, "dq.series_last", probe._monitor_samples[-1]["value"], 9)

	probe.free()