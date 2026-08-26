extends Area2D

const SPEED := 500.0
const MAX_RANGE := 400.0
var direction := Vector2.RIGHT
var damage := 15.0
var lifetime := 2.0
var _distance_traveled := 0.0

func _ready() -> void:
	body_entered.connect(_on_body_entered)

func _physics_process(delta: float) -> void:
	var move := direction * SPEED * delta
	position += move
	_distance_traveled += move.length()
	lifetime -= delta
	if lifetime <= 0.0 or _distance_traveled >= MAX_RANGE:
		queue_free()

func launch(dir: Vector2) -> void:
	direction = dir.normalized()
	rotation = direction.angle()

func _on_body_entered(body: Node) -> void:
	if body.is_in_group("enemies"):
		body.take_damage(damage)
		queue_free()