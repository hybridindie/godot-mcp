extends CharacterBody2D
## Enemy character for Vampire Survivors demo.

@export var speed: float = 100.0
@export var max_health: int = 30
@export var contact_damage: int = 10
@export var xp_value: int = 10

var health: int
var player: Node2D

@onready var health_bar: ProgressBar = $HealthBar

func _ready() -> void:
	add_to_group("enemies")
	motion_mode = MOTION_MODE_FLOATING
	health = max_health
	_update_health_bar()
	
	# Find player in scene
	player = get_node_or_null("../Player")
	
	# Connect hurtbox to detect player body contact
	var hurtbox = get_node_or_null("Hurtbox")
	if hurtbox is Area2D:
		hurtbox.body_entered.connect(_on_hurtbox_body_entered)

func _physics_process(_delta: float) -> void:
	if player == null or not player.alive:
		velocity = Vector2.ZERO
		move_and_slide()
		return
	
	# Chase player
	var direction := (player.global_position - global_position).normalized()
	velocity = direction * speed
	move_and_slide()

func take_damage(amount: int) -> void:
	health -= amount
	_update_health_bar()
	if health <= 0:
		_die()

func get_contact_damage() -> int:
	return contact_damage

func _die() -> void:
	GameManager.update_score(GameManager.get_score() + 1)
	
	# Spawn XP gem (deferred to avoid physics query flush conflict)
	var xp_scene = load("res://scenes/xp_gem.tscn")
	if xp_scene:
		var gem = xp_scene.instantiate()
		gem.global_position = global_position
		gem.xp_value = xp_value
		get_parent().call_deferred("add_child", gem)
	
	# Spawn death particles (deferred)
	var particles = get_node_or_null("../DeathParticles")
	if particles is GPUParticles2D:
		particles.global_position = global_position
		particles.restart()
		particles.call_deferred("set", "emitting", true)
	
	queue_free()

func _update_health_bar() -> void:
	if health_bar:
		health_bar.max_value = max_health
		health_bar.value = health

func _on_hurtbox_body_entered(body: Node2D) -> void:
	# Damage the player on contact
	if body.is_in_group("player"):
		if body.has_method("take_damage"):
			body.take_damage(contact_damage)
