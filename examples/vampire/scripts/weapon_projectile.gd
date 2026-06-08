extends Node2D
## Projectile weapon controller for Vampire Survivors demo.

@export var projectile_speed: float = 400.0
@export var projectile_lifetime: float = 3.0

var player: Node2D
var shoot_timer: float = 0.0

func _ready() -> void:
	player = get_parent()

func _process(delta: float) -> void:
	shoot_timer -= delta
	if shoot_timer <= 0 and player is Node2D and player.alive:
		_shoot()
		shoot_timer = player.attack_speed

func _shoot() -> void:
	var enemies := get_tree().get_nodes_in_group("enemies")
	if enemies.is_empty():
		return
	
	var player_pos = player.global_position
	enemies.sort_custom(func(a, b):
		return player_pos.distance_to(a.global_position) < player_pos.distance_to(b.global_position)
	)
	
	var count := mini(player.projectile_count, enemies.size())
	for i in range(count):
		var target = enemies[i]
		_spawn_projectile(target)

func _spawn_projectile(target: Node2D) -> void:
	var projectile = CharacterBody2D.new()
	projectile.add_to_group("projectiles")
	
	# Visual: small yellow circle
	var sprite = ColorRect.new()
	sprite.offset_left = -4
	sprite.offset_top = -4
	sprite.offset_right = 4
	sprite.offset_bottom = 4
	sprite.color = Color(0.8, 0.8, 0.2, 1)
	projectile.add_child(sprite)
	
	# Collision
	var collision = CollisionShape2D.new()
	var shape = CircleShape2D.new()
	shape.radius = 4
	collision.shape = shape
	projectile.add_child(collision)
	
	# Hurtbox (Area2D) — detects enemy BODIES on layer 4
	var hurtbox = Area2D.new()
	hurtbox.collision_layer = 0
	hurtbox.collision_mask = 4
	var hurt_shape = CollisionShape2D.new()
	var hurt_circle = CircleShape2D.new()
	hurt_circle.radius = 6
	hurt_shape.shape = hurt_circle
	hurtbox.add_child(hurt_shape)
	projectile.add_child(hurtbox)
	
	projectile.set_meta("target", target)
	projectile.set_meta("speed", projectile_speed)
	projectile.set_meta("damage", player.damage)

	projectile.global_position = player.global_position
	get_tree().root.add_child(projectile)
	
	# Connect to BODY entered (detects CharacterBody2D enemies on layer 4)
	hurtbox.body_entered.connect(_on_projectile_hit.bind(projectile))
	
	await get_tree().create_timer(projectile_lifetime).timeout
	if is_instance_valid(projectile):
		projectile.queue_free()

func _on_projectile_hit(body: Node2D, projectile: Node) -> void:
	if body is CharacterBody2D and body.is_in_group("enemies"):
		if body.has_method("take_damage"):
			body.take_damage(projectile.get_meta("damage"))
	if is_instance_valid(projectile):
		projectile.queue_free()

func _physics_process(_delta: float) -> void:
	for projectile in get_tree().get_nodes_in_group("projectiles"):
		if not is_instance_valid(projectile):
			continue
		if projectile is CharacterBody2D:
			var target = projectile.get_meta("target")
			if not is_instance_valid(target):
				projectile.queue_free()
				continue
			var dir = (target.global_position - projectile.global_position).normalized()
			projectile.velocity = dir * projectile.get_meta("speed")
			projectile.move_and_slide()
