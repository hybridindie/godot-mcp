extends Area2D
## Area-of-effect weapon for Vampire Survivors demo.
## This weapon deals damage to all enemies in its radius on a timer.

@export var tick_rate: float = 1.0
@export var damage_multiplier: float = 0.5

var player: Node2D
var tick_timer: float = 0.0

func _ready() -> void:
	player = get_parent()

func _process(delta: float) -> void:
	tick_timer -= delta
	if tick_timer <= 0 and player is Node2D and player.alive:
		_tick_damage()
		tick_timer = tick_rate

func _tick_damage() -> void:
	# Detect enemy BODIES (CharacterBody2D on layer 4) overlapping the hitbox
	var hitbox = get_node_or_null("Hitbox")
	if hitbox == null:
		return
	
	var bodies = hitbox.get_overlapping_bodies()
	for body in bodies:
		if body is CharacterBody2D and body.is_in_group("enemies"):
			if body.has_method("take_damage"):
				body.take_damage(int(player.damage * damage_multiplier))
