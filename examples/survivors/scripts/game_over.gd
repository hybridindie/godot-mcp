extends Control

@onready var label: Label = $VB/Label
@onready var button: Button = $VB/Button

func _ready() -> void:
	visible = true
	# Don't let the overlay block input from reaching GameManager._unhandled_input.
	# The Button still receives clicks because it has its own mouse_filter.
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	var gm := get_node_or_null("/root/GameManager")
	if gm:
		gm.state_changed.connect(_on_state_changed)
		_on_state_changed(gm.state)
	button.pressed.connect(_on_button)

func _on_state_changed(new_state: int) -> void:
	match new_state:
		0:  # MENU
			_show("SURVIVORS", "Press SPACE or click Start", "Start")
		1:  # PLAYING
			_hide()
		2:  # PAUSED
			_show("PAUSED", "Press ESC or click Resume", "Resume")
		3:  # GAME_OVER
			var gm := get_node_or_null("/root/GameManager")
			if gm:
				_show("GAME OVER", "Score: %d   Wave: %d" % [gm.score, gm.wave], "Retry")
			else:
				_show("GAME OVER", "", "Retry")

func _show(title: String, subtitle: String, btn_text: String) -> void:
	visible = true
	label.text = title + ("\n" + subtitle if subtitle != "" else "")
	button.text = btn_text

func _hide() -> void:
	visible = false

func _on_button() -> void:
	var gm := get_node_or_null("/root/GameManager")
	if gm == null:
		return
	match gm.state:
		0:  # MENU -> start
			gm.start_game()
		2:  # PAUSED -> resume
			gm._change_state(1)  # PLAYING
		3:  # GAME_OVER -> retry
			gm.start_game()