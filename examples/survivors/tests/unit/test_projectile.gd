extends GutTest

# Tests for the projectile script — launch direction, speed, lifetime,
# max range, damage on enemy contact, no damage on non-enemies.

var _proj: Area2D


func before_each() -> void:
	_proj = Area2D.new()
	_proj.set_script(load("res://scripts/projectile.gd"))
	var col := CollisionShape2D.new()
	var shape := RectangleShape2D.new()
	shape.size = Vector2(12, 4)
	col.shape = shape
	_proj.add_child(col)
	add_child(_proj)


func after_each() -> void:
	_proj.free()


func test_projectile_starts_with_default_damage() -> void:
	assert_eq(_proj.damage, 15.0, "Default projectile damage is 15")


func test_projectile_starts_with_default_lifetime() -> void:
	assert_eq(_proj.lifetime, 2.0, "Default lifetime is 2 seconds")


func test_projectile_has_max_range() -> void:
	assert_eq(_proj.MAX_RANGE, 400.0, "Max range should be 400 pixels")


func test_projectile_starts_with_zero_distance() -> void:
	assert_eq(_proj._distance_traveled, 0.0, "Distance traveled starts at 0")


func test_projectile_starts_facing_right() -> void:
	assert_eq(_proj.direction, Vector2.RIGHT, "Default direction is RIGHT")
	assert_eq(_proj.rotation, 0.0, "Default rotation is 0 (facing right)")


func test_launch_sets_direction_normalized() -> void:
	_proj.launch(Vector2(3, 4))
	assert_eq(_proj.direction, Vector2(0.6, 0.8), "Launch normalizes the direction vector")


func test_launch_sets_rotation_to_angle() -> void:
	_proj.launch(Vector2(0, 1))
	assert_almost_eq(_proj.rotation, PI / 2.0, 0.001, "Launching down rotates 90 degrees")


func test_launch_left_rotates_180() -> void:
	_proj.launch(Vector2(-1, 0))
	assert_almost_eq(_proj.rotation, PI, 0.001, "Launching left rotates 180 degrees")


func test_lifetime_decreases_in_physics_process() -> void:
	var initial: float = _proj.lifetime
	_proj._physics_process(0.5)
	assert_lt(_proj.lifetime, initial, "Lifetime should decrease after _physics_process")


func test_distance_increases_in_physics_process() -> void:
	_proj._physics_process(0.1)
	assert_gt(_proj._distance_traveled, 0.0, "Distance should increase after moving")


func test_on_body_entered_enemy_takes_damage() -> void:
	var enemy := CharacterBody2D.new()
	enemy.add_to_group("enemies")
	enemy.set("health", 30.0)
	enemy.set("damage", 10.0)
	enemy.set_script(load("res://scripts/enemy.gd"))
	add_child(enemy)
	enemy.health = 30.0
	_proj._on_body_entered(enemy)
	assert_lt(enemy.health, 30.0, "Enemy health should decrease after projectile hit")
	enemy.free()


func test_on_body_entered_non_enemy_is_ignored() -> void:
	var npc := CharacterBody2D.new()
	add_child(npc)
	_proj._on_body_entered(npc)
	assert_true(is_instance_valid(_proj), "Projectile should survive hitting a non-enemy")
	npc.free()