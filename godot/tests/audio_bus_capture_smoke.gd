@tool
extends SceneTree
## Headless behavior test for MCPAudioBusCapture (issue #219 G8).
##
## Run via: godot --headless --path godot/ --script res://tests/audio_bus_capture_smoke.gd
## Exercises capture → remove_bus → restore against the live AudioServer (available
## headlessly) to prove a removed bus round-trips with its properties and effect stack —
## which is exactly what the remove handler's UndoRedo undo step relies on.

const AudioBusCapture := preload("res://addons/godot_mcp/audio_bus_capture.gd")


func _initialize() -> void:
	var failures: Array[String] = []

	# Build a bus with a couple of properties + a (disabled) reverb effect.
	var index := AudioServer.get_bus_count()
	AudioServer.add_bus(index)
	AudioServer.set_bus_name(index, "SFX")
	AudioServer.set_bus_volume_db(index, -6.0)
	AudioServer.set_bus_send(index, "Master")
	AudioServer.set_bus_mute(index, true)
	var reverb := AudioEffectReverb.new()
	AudioServer.add_bus_effect(index, reverb, 0)
	AudioServer.set_bus_effect_enabled(index, 0, false)

	# Capture, then remove the bus.
	var state := AudioBusCapture.capture(index)
	_eq(failures, "captured.name", state.get("name"), "SFX")
	_eq(failures, "captured.effects", (state.get("effects") as Array).size(), 1)
	AudioServer.remove_bus(index)
	if AudioServer.get_bus_index("SFX") != -1:
		failures.append("bus 'SFX' still present after remove_bus")

	# Restore at the same index and verify everything came back.
	AudioBusCapture.restore(index, state)
	var restored := AudioServer.get_bus_index("SFX")
	if restored != index:
		failures.append("restored bus index: expected %d, got %d" % [index, restored])
	else:
		_eq(failures, "restored.volume_db", AudioServer.get_bus_volume_db(restored), -6.0)
		_eq(failures, "restored.send", String(AudioServer.get_bus_send(restored)), "Master")
		_eq(failures, "restored.mute", AudioServer.is_bus_mute(restored), true)
		_eq(failures, "restored.effect_count", AudioServer.get_bus_effect_count(restored), 1)
		_eq(failures, "restored.effect_is_reverb", AudioServer.get_bus_effect(restored, 0) is AudioEffectReverb, true)
		_eq(failures, "restored.effect_enabled", AudioServer.is_bus_effect_enabled(restored, 0), false)
		AudioServer.remove_bus(restored)  # leave the layout clean

	if failures.is_empty():
		print("AUDIO_BUS_CAPTURE_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("AUDIO_BUS_CAPTURE_TEST_FAIL")
		quit(1)


func _eq(failures: Array[String], label: String, got: Variant, want: Variant) -> void:
	if got != want:
		failures.append("%s: expected %s, got %s" % [label, str(want), str(got)])
