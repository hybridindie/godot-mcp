extends Node2D
## Debugger Demo for Vampire Survivors example.
##
## Attach this to a node in the main scene, then use the MCP debugger tools to
## inspect execution when a breakpoint is hit inside _process or on_button_press.

@export var demo_enabled: bool = true
@export var tick_interval: float = 2.0

var _tick_timer: float = 0.0
var _counters: Dictionary = {"a": 0, "b": 0}
var _history: Array = []

func _ready() -> void:
	print("DebuggerDemo ready — game will auto-pause in 2 seconds for debugger demo.")
	# Auto-pause after 2 seconds so we can test debugger tools without manual input
	await get_tree().create_timer(2.0).timeout
	breakpoint

func _process(delta: float) -> void:
	# Check for MCP force_break request
	MCPRuntimeProbe.check_force_break()
	
	if not demo_enabled:
		return
	_tick_timer += delta
	if _tick_timer >= tick_interval:
		_tick_timer = 0.0
		_run_debug_tick()

func _run_debug_tick() -> void:
	# Local variables for the debugger to inspect
	var local_sum: int = 0
	var local_items: Array = []
	
	for i in range(3):
		var item_value: int = i * 10 + _counters["a"]
		local_items.append(item_value)
		local_sum += item_value
	
	var average: float = local_sum / float(local_items.size())
	
	_history.append({"sum": local_sum, "avg": average, "items": local_items.duplicate()})
	if _history.size() > 10:
		_history.pop_front()
	
	_counters["a"] += 1
	_counters["b"] = int(average)
	
	print("Tick: sum=%d avg=%.1f counters=%s" % [local_sum, average, _counters])

func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_SPACE:
		_trigger_debuggable_action()
	if event is InputEventMouseButton and event.pressed:
		_trigger_debuggable_action()

func _trigger_debuggable_action() -> void:
	# Another function with locals — useful for "step into / step over" demos
	var before: int = _counters["a"]
	var after: int = _recalculate(before, _counters["b"])
	_counters["a"] = after
	print("Action: before=%d after=%d" % [before, after])
	# Auto-breakpoint for MCP debugger demonstration
	breakpoint

func _recalculate(base: int, multiplier: int) -> int:
	# A helper function to demonstrate "step into"
	var step1: int = base * 2
	var step2: int = step1 + multiplier
	var result: int = step2 % 100
	return result

func get_history() -> Array:
	return _history.duplicate()

func get_counters() -> Dictionary:
	return _counters.duplicate()
