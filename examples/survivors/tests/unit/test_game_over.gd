extends GutTest

# Tests for the game_over overlay script — state-driven visibility, button
# labels per state, button actions (start/resume/retry), and the signal
# contract with GameManager.state_changed.
#
# The overlay is a Control inside the HUD CanvasLayer of the main scene.
# We instantiate the full main scene so _ready fires and connects signals.

var _main: Node2D
var _overlay: Control
var _gm: Node


func before_each() -> void:
	# Reset the GameManager singleton — its state persists across tests.
	_gm = get_node("/root/GameManager")
	_gm._change_state(_gm.State.MENU)
	var scene: PackedScene = load("res://scenes/main.tscn")
	_main = scene.instantiate() as Node2D
	add_child(_main)
	_overlay = _main.get_node("HUD/GameOverScreen") as Control


func after_each() -> void:
	_main.free()


func test_overlay_visible_on_start() -> void:
	# GameManager starts in MENU state, overlay should be visible.
	assert_true(_overlay.visible, "Overlay should be visible in MENU state")


func test_overlay_hidden_when_playing() -> void:
	_gm.start_game()
	assert_false(_overlay.visible, "Overlay should be hidden when PLAYING")


func test_overlay_visible_when_paused() -> void:
	_gm.start_game()
	_gm._change_state(_gm.State.PAUSED)
	assert_true(_overlay.visible, "Overlay should be visible when PAUSED")


func test_overlay_visible_on_game_over() -> void:
	_gm.start_game()
	_gm.end_game()
	assert_true(_overlay.visible, "Overlay should be visible on GAME_OVER")


func test_button_text_changes_per_state() -> void:
	# MENU -> "Start"
	var button: Button = _overlay.get_node("VB/Button") as Button
	assert_eq(button.text, "Start", "Button should say 'Start' in MENU state")

	# PLAYING -> hidden, but let's check PAUSED -> "Resume"
	_gm.start_game()
	_gm._change_state(_gm.State.PAUSED)
	assert_eq(button.text, "Resume", "Button should say 'Resume' when PAUSED")

	# GAME_OVER -> "Retry"
	_gm.end_game()
	assert_eq(button.text, "Retry", "Button should say 'Retry' on GAME_OVER")


func test_label_shows_score_on_game_over() -> void:
	_gm.start_game()
	_gm.score = 500
	_gm.wave = 7
	_gm.end_game()
	var label: Label = _overlay.get_node("VB/Label") as Label
	assert_string_contains(label.text, "500", "Game over label should show score")
	assert_string_contains(label.text, "7", "Game over label should show wave")


func test_start_button_transitions_to_playing() -> void:
	# In MENU state, pressing the button should start the game.
	assert_eq(_gm.state, _gm.State.MENU)
	var button: Button = _overlay.get_node("VB/Button") as Button
	button.emit_signal("pressed")
	assert_eq(_gm.state, _gm.State.PLAYING, "Start button should transition to PLAYING")


func test_retry_button_resets_and_starts() -> void:
	# Go to GAME_OVER, then press retry.
	_gm.start_game()
	_gm.score = 999
	_gm.end_game()
	assert_eq(_gm.state, _gm.State.GAME_OVER)

	var button: Button = _overlay.get_node("VB/Button") as Button
	button.emit_signal("pressed")
	assert_eq(_gm.state, _gm.State.PLAYING, "Retry should transition to PLAYING")
	assert_eq(_gm.score, 0, "Retry should reset score to 0")
	assert_eq(_gm.wave, 1, "Retry should reset wave to 1")