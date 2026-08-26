extends GutTest

# Tests for the enemy script — health, damage, death signal, group membership.

var _enemy: CharacterBody2D


func before_each() -> void:
	var scene := load("res://scenes/enemy.tscn") as PackedScene
	_enemy = scene.instantiate() as CharacterBody2D
	add_child(_enemy)
	await wait_for_signal(_enemy.ready, 1.0)


func after_each() -> void:
	_enemy.free()


func test_enemy_in_enemies_group() -> void:
	assert_true(_enemy.is_in_group("enemies"), "Enemy should be in 'enemies' group")


func test_enemy_starts_with_default_health() -> void:
	assert_eq(_enemy.health, 30.0, "Default enemy health is 30")
	assert_eq(_enemy.max_health, 30.0, "Default max_health is 30")


func test_enemy_has_damage_value() -> void:
	assert_gt(_enemy.damage, 0.0, "Enemy should have positive damage")


func test_take_damage_reduces_health() -> void:
	_enemy.take_damage(10.0)
	assert_eq(_enemy.health, 20.0, "30 - 10 = 20 HP")


func test_take_damage_emits_enemy_died_at_zero() -> void:
	watch_signals(_enemy)
	_enemy.take_damage(30.0)
	assert_signal_emitted(_enemy, "enemy_died")


func test_take_damage_does_not_emit_above_zero() -> void:
	watch_signals(_enemy)
	_enemy.take_damage(10.0)
	assert_signal_not_emitted(_enemy, "enemy_died")