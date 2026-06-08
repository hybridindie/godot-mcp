extends Node
## Game manager autoload singleton for Vampire Survivors demo.
## This script is registered as an autoload in project.godot.

var score: int = 0
var wave: int = 1
var game_time: float = 0.0
var paused: bool = false
var game_over_state: bool = false

func _ready() -> void:
	# Autoload runs at root level; we don't have scene access here yet
	pass

func _process(delta: float) -> void:
	if not paused and not game_over_state:
		game_time += delta
		_update_time_display()

func _get_main() -> Node:
	return get_node_or_null("/root/Main")

func _get_hud() -> Node:
	var main = _get_main()
	if main:
		return main.get_node_or_null("HUD")
	return null

func _get_upgrade_menu() -> Node:
	var main = _get_main()
	if main:
		return main.get_node_or_null("UpgradeMenu")
	return null

func _get_game_over_screen() -> Node:
	var main = _get_main()
	if main:
		return main.get_node_or_null("GameOverScreen")
	return null

func _get_player() -> Node:
	var main = _get_main()
	if main:
		return main.get_node_or_null("Player")
	return null

func _get_spawner() -> Node:
	var main = _get_main()
	if main:
		return main.get_node_or_null("EnemySpawner")
	return null

func update_score(kills: int) -> void:
	score = kills
	var hud = _get_hud()
	if hud and hud.has_method("update_score"):
		hud.update_score(score)

func update_wave(new_wave: int) -> void:
	wave = new_wave
	var hud = _get_hud()
	if hud and hud.has_method("update_wave"):
		hud.update_wave(wave)

func _update_time_display() -> void:
	var hud = _get_hud()
	if hud and hud.has_method("update_time"):
		hud.update_time(game_time)

func show_upgrade_menu() -> void:
	paused = true
	get_tree().paused = true
	var menu = _get_upgrade_menu()
	if menu:
		menu.visible = true
		if menu.has_method("generate_options"):
			menu.generate_options()

func hide_upgrade_menu() -> void:
	paused = false
	get_tree().paused = false
	var menu = _get_upgrade_menu()
	if menu:
		menu.visible = false

func apply_upgrade(upgrade_type: String) -> void:
	var player = _get_player()
	if player and player.has_method("apply_upgrade"):
		player.apply_upgrade(upgrade_type)
	hide_upgrade_menu()

func game_over() -> void:
	game_over_state = true
	var screen = _get_game_over_screen()
	if screen:
		screen.visible = true
		var score_label = screen.get_node_or_null("Panel/VBoxContainer/Score")
		if score_label:
			score_label.text = "Score: %d | Wave: %d | Time: %.1fs" % [score, wave, game_time]
	get_tree().paused = true

func restart() -> void:
	# Reset state
	score = 0
	wave = 1
	game_time = 0.0
	paused = false
	game_over_state = false
	
	get_tree().paused = false
	# Use call_deferred so the unpause takes effect before the scene is freed.
	get_tree().call_deferred("reload_current_scene")

func get_score() -> int:
	return score

func get_wave() -> int:
	return wave

func get_time() -> float:
	return game_time

func is_game_over() -> bool:
	return game_over_state
