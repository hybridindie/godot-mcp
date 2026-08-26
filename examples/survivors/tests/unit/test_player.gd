extends GutTest

# Tests for the player script — health, XP, leveling, damage, death signals.
# We instantiate just a CharacterBody2D with the player script (not the whole
# main scene, which would generate the world background + obstacles).

var _player: CharacterBody2D


func before_each() -> void:
	_player = CharacterBody2D.new()
	_player.set_script(load("res://scripts/player.gd"))
	add_child(_player)
	# _ready fires synchronously on add_child when not inside a SceneTree cycle;
	# no need to await.


func after_each() -> void:
	_player.free()


func test_player_starts_with_full_health() -> void:
	assert_eq(_player.health, 100.0, "Player should start at 100 HP")
	assert_eq(_player.max_health, 100.0, "Max health should be 100")


func test_player_starts_at_level_1() -> void:
	assert_eq(_player.level, 1, "Player should start at level 1")
	assert_eq(_player.xp, 0, "Player should start with 0 XP")
	assert_eq(_player.xp_to_next, 5, "First level threshold is 5 XP")


func test_take_damage_reduces_health() -> void:
	_player.take_damage(30.0)
	assert_eq(_player.health, 70.0, "30 damage from 100 = 70 HP")


func test_take_damage_clamps_at_zero() -> void:
	_player.take_damage(200.0)
	assert_eq(_player.health, 0.0, "Health clamps at 0")


func test_take_damage_emits_health_changed() -> void:
	watch_signals(_player)
	_player.take_damage(10.0)
	assert_signal_emitted(_player, "health_changed")


func test_death_emits_died_signal() -> void:
	watch_signals(_player)
	_player.take_damage(100.0)
	assert_signal_emitted(_player, "died")


func test_gain_xp_increments_xp() -> void:
	_player.gain_xp(3)
	assert_eq(_player.xp, 3, "3 XP gained")
	assert_eq(_player.level, 1, "No level up yet (need 5)")


func test_gain_xp_level_ups_at_threshold() -> void:
	_player.gain_xp(5)
	assert_eq(_player.level, 2, "5 XP = level 2")
	assert_eq(_player.xp, 0, "XP resets on level up")
	assert_eq(_player.xp_to_next, 7, "Next threshold is 5 * 1.5 = 7")


func test_level_up_increases_max_health_and_heals() -> void:
	var initial_max: float = _player.max_health
	_player.gain_xp(5)
	assert_eq(_player.max_health, initial_max + 10.0, "Level up adds 10 max HP")
	# heal is min(max_health, health + 20) — capped at the new max (110).
	assert_eq(_player.health, _player.max_health, "Level up heals to full (capped at max_health)")


func test_multiple_level_ups_in_one_gain() -> void:
	# 5 + 7 = 12 XP needed for two levels; give 14 to overflow past both.
	_player.gain_xp(14)
	assert_eq(_player.level, 3, "14 XP = two level ups -> level 3")
	# After level 2: xp_to_next = 7, spent 5, remaining 9.
	# After level 3: xp_to_next = int(7*1.5) = 10, spent 7, remaining 2.
	assert_eq(_player.xp, 2, "Leftover XP after two level ups")