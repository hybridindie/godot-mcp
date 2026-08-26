extends GutTest

# Tests for the GameManager state machine and game loop logic.
# The GameManager is an autoload, so we access it via /root/GameManager.

var _gm: Node


func before_each() -> void:
	_gm = get_node("/root/GameManager")
	assert_not_null(_gm, "GameManager autoload should be present")


func test_game_starts_in_menu_state() -> void:
	# The autoload _ready sets MENU state.
	assert_eq(_gm.state, _gm.State.MENU, "Game should start in MENU state")


func test_state_enum_has_four_states() -> void:
	assert_eq(_gm.State.MENU, 0, "MENU = 0")
	assert_eq(_gm.State.PLAYING, 1, "PLAYING = 1")
	assert_eq(_gm.State.PAUSED, 2, "PAUSED = 2")
	assert_eq(_gm.State.GAME_OVER, 3, "GAME_OVER = 3")


func test_start_game_transitions_to_playing() -> void:
	_gm.start_game()
	assert_eq(_gm.state, _gm.State.PLAYING, "start_game() -> PLAYING")
	assert_false(get_tree().paused, "PLAYING should not pause the tree")


func test_end_game_transitions_to_game_over() -> void:
	_gm.start_game()
	_gm.end_game()
	assert_eq(_gm.state, _gm.State.GAME_OVER, "end_game() -> GAME_OVER")
	assert_true(get_tree().paused, "GAME_OVER should pause the tree")


func test_start_game_resets_score_and_wave() -> void:
	_gm.score = 999
	_gm.wave = 42
	_gm.start_game()
	assert_eq(_gm.score, 0, "Score resets to 0 on start_game")
	assert_eq(_gm.wave, 1, "Wave resets to 1 on start_game")


func test_start_game_resets_spawn_timing() -> void:
	_gm.spawn_interval = 0.1
	_gm.spawn_timer = 99.0
	_gm.start_game()
	assert_eq(_gm.spawn_interval, 2.0, "spawn_interval resets to 2.0")
	assert_eq(_gm.spawn_timer, 0.0, "spawn_timer resets to 0")


func test_state_changed_signal_emitted_on_transition() -> void:
	watch_signals(_gm)
	_gm.start_game()
	assert_signal_emitted(_gm, "state_changed")


func test_game_over_signal_no_longer_exists() -> void:
	# Regression test: the old 'game_over' signal was replaced by 'state_changed'.
	# hud.gd used to connect to gm.game_over — that broke when we removed it.
	# This test pins that game_over is NOT a valid signal on GameManager.
	var sigs := _gm.get_signal_list()
	for sig in sigs:
		assert_ne(sig["name"], "game_over", "game_over signal should be removed; use state_changed")