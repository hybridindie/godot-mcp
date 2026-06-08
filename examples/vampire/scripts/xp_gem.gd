extends Area2D
## XP gem dropped by defeated enemies.
## Player magnet sets `velocity` directly; gem follows it and gets consumed on body collision.

@export var xp_value: int = 10

var velocity := Vector2.ZERO
var _consumed := false

func _ready() -> void:
	add_to_group("xp_gems")
	body_entered.connect(_on_body_entered)

func _physics_process(delta: float) -> void:
	# Apply any velocity set by player magnet (or other sources)
	if velocity != Vector2.ZERO:
		position += velocity * delta

func _on_body_entered(body: Node2D) -> void:
	if _consumed:
		return
	if body.is_in_group("player"):
		_consumed = true
		_collect(body)

func _collect(player: Node2D) -> void:
	# Spawn pickup particles
	var particles = get_node_or_null("../XPPickupParticles")
	if particles is GPUParticles2D:
		particles.global_position = global_position
		particles.restart()
		particles.emitting = true
	
	# Give XP to player
	if player.has_method("gain_xp"):
		player.gain_xp(xp_value)
	
	queue_free()
