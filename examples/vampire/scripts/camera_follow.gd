extends Camera2D
## Simple camera that follows the player.

@export var follow_speed: float = 5.0

var player: Node2D

func _ready() -> void:
	player = get_node_or_null("../Player")

func _process(delta: float) -> void:
	if player != null:
		position = position.lerp(player.global_position, follow_speed * delta)
