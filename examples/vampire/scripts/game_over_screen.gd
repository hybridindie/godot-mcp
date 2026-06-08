extends CanvasLayer
## Game Over screen handler for Vampire Survivors demo.
## Must process during pause so the Restart button works while the tree is frozen.

func _ready() -> void:
	# Keep this UI alive during pause so the Restart button can be clicked
	process_mode = Node.PROCESS_MODE_ALWAYS
	
	var restart_button = $Panel/VBoxContainer/RestartButton
	restart_button.process_mode = Node.PROCESS_MODE_ALWAYS
	restart_button.pressed.connect(_on_restart)

func _on_restart() -> void:
	# Unpause before reload so the tree isn't frozen during scene transition
	get_tree().paused = false
	get_tree().call_deferred("reload_current_scene")
