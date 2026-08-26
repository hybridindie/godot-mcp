extends Area2D

const PICKUP_RADIUS := 80.0
const MAGNET_SPEED := 400.0
var picked_up := false

func _ready() -> void:
	add_to_group("xp_gems")
	body_entered.connect(_on_body_entered)

func _physics_process(delta: float) -> void:
	var player: Node2D = get_tree().get_first_node_in_group("player")
	if player == null:
		return
	var dist := global_position.distance_to(player.global_position)
	if dist < PICKUP_RADIUS:
		var dir: Vector2 = (player.global_position - global_position).normalized()
		position += dir * MAGNET_SPEED * delta

func _on_body_entered(body: Node) -> void:
	if body.is_in_group("player") and not picked_up:
		picked_up = true
		body.gain_xp(1)
		queue_free()