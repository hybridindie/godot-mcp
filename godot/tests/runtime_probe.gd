extends Node
## Runtime e2e fixture (issue #13): prints a marker and quits, so a headless run
## produces capturable output and a clean exit. Not @tool — this runs at game time.


func _ready() -> void:
	print("RUNTIME_PROBE_OK")
	get_tree().quit()
