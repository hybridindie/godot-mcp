extends CharacterBody2D

const SPEED := 150.0
var health := 30.0
var max_health := 30.0
var damage := 10.0
var xp_value := 1

signal enemy_died(pos: Vector2, xp_val: int)

func _ready() -> void:
	add_to_group("enemies")
	collision_mask = 18

func _physics_process(_delta: float) -> void:
	var player: Node2D = get_tree().get_first_node_in_group("player")
	if player == null:
		return
	var dir: Vector2 = (player.global_position - global_position).normalized()
	velocity = dir * SPEED
	move_and_slide()

func take_damage(amount: float) -> void:
	health -= amount
	if health <= 0.0:
		enemy_died.emit(global_position, xp_value)
		queue_free()
