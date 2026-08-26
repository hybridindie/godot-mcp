extends GutTest

# Tests for the XP gem script — group membership, pickup state,
# magnet behavior, XP grant on player contact, no double-pickup.

var _gem: Area2D


func before_each() -> void:
	_gem = Area2D.new()
	_gem.set_script(load("res://scripts/xp_gem.gd"))
	var col := CollisionShape2D.new()
	var shape := RectangleShape2D.new()
	shape.size = Vector2(10, 10)
	col.shape = shape
	_gem.add_child(col)
	add_child(_gem)


func after_each() -> void:
	if is_instance_valid(_gem):
		_gem.free()


func test_gem_in_xp_gems_group() -> void:
	assert_true(_gem.is_in_group("xp_gems"), "Gem should be in 'xp_gems' group")


func test_gem_starts_not_picked_up() -> void:
	assert_false(_gem.picked_up, "Gem should start not picked up")


func test_on_body_entered_player_grants_xp() -> void:
	# Create a fake player with the player script so gain_xp exists.
	var player := CharacterBody2D.new()
	player.add_to_group("player")
	player.set_script(load("res://scripts/player.gd"))
	add_child(player)
	var xp_before: int = player.xp
	_gem._on_body_entered(player)
	assert_eq(player.xp, xp_before + 1, "Player should gain 1 XP from gem pickup")
	player.free()


func test_on_body_entered_non_player_is_ignored() -> void:
	var npc := CharacterBody2D.new()
	add_child(npc)
	_gem._on_body_entered(npc)
	assert_false(_gem.picked_up, "Gem should not be picked up by non-player")
	npc.free()


func test_pickup_sets_flag_and_frees_gem() -> void:
	var player := CharacterBody2D.new()
	player.add_to_group("player")
	player.set_script(load("res://scripts/player.gd"))
	add_child(player)
	_gem._on_body_entered(player)
	# queue_free is deferred — the flag is set synchronously.
	assert_true(_gem.picked_up, "picked_up flag should be set before queue_free")
	player.free()


func test_double_pickup_is_prevented() -> void:
	var player := CharacterBody2D.new()
	player.add_to_group("player")
	player.set_script(load("res://scripts/player.gd"))
	add_child(player)
	var xp_before: int = player.xp
	# First pickup
	_gem._on_body_entered(player)
	# Second pickup attempt — should be a no-op (picked_up guard)
	_gem._on_body_entered(player)
	assert_eq(player.xp, xp_before + 1, "Only 1 XP should be granted (no double pickup)")
	player.free()