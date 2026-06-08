extends CharacterBody2D
## Player character for Vampire Survivors demo.

@export var speed: float = 200.0
@export var max_health: int = 100
@export var damage: int = 10
@export var attack_speed: float = 1.0
@export var projectile_count: int = 1
@export var area_size: float = 60.0
@export var magnet_range: float = 80.0

var health: int
var xp: int = 0
var xp_to_next_level: int = 100
var level: int = 1
var alive: bool = true

@onready var weapon_projectile: Node2D = $WeaponProjectile
@onready var weapon_area: Area2D = $WeaponArea
@onready var hurtbox: Area2D = $Hurtbox

func _ready() -> void:
	add_to_group("player")
	motion_mode = MOTION_MODE_FLOATING
	wall_min_slide_angle = PI
	floor_max_angle = 0
	health = max_health
	hurtbox.body_entered.connect(_on_hurtbox_body_entered)
	weapon_area.get_node("Hitbox").body_entered.connect(_on_area_weapon_hit)
	_update_weapon_area()

func _draw() -> void:
	# Draw a blue circle to distinguish from enemy squares
	draw_circle(Vector2.ZERO, 20.0, Color(0.2, 0.6, 1, 1))

func _physics_process(delta: float) -> void:
	if not alive:
		return
	
	# WASD / arrow key movement
	var direction := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
	velocity = direction * speed
	
	# Direct wall clamping — no physics snap
	position += velocity * delta
	
	# Clamp to arena bounds (with margin for player radius ~20)
	var margin := 20.0
	position.x = clampf(position.x, -1024.0 + margin, 1024.0 - margin)
	position.y = clampf(position.y, -768.0 + margin, 768.0 - margin)
	
	# Magnet: pull nearby XP gems toward player
	_pull_xp(delta)

func take_damage(amount: int) -> void:
	health -= amount
	if health <= 0:
		health = 0
		_die()
	_update_hud()

func heal(amount: int) -> void:
	health = mini(health + amount, max_health)
	_update_hud()

func gain_xp(amount: int) -> void:
	xp += amount
	_update_hud()
	if xp >= xp_to_next_level:
		_level_up()

func _die() -> void:
	alive = false
	visible = false
	velocity = Vector2.ZERO
	GameManager.game_over()

func _level_up() -> void:
	level += 1
	xp -= xp_to_next_level
	xp_to_next_level = int(xp_to_next_level * 1.5)
	_update_hud()
	GameManager.show_upgrade_menu()

func _on_hurtbox_body_entered(body: Node2D) -> void:
	# Check if it's an enemy body
	if body is CharacterBody2D and body.is_in_group("enemies"):
		if body.has_method("get_contact_damage"):
			take_damage(body.get_contact_damage())

func _pull_xp(delta: float) -> void:
	for gem in get_tree().get_nodes_in_group("xp_gems"):
		if not is_instance_valid(gem):
			continue
		var dist := global_position.distance_to(gem.global_position)
		if dist < magnet_range:
			var pull_dir: Vector2 = (global_position - gem.global_position).normalized()
			var strength := 1.0 - (dist / magnet_range)
			var speed := 200.0 + 400.0 * strength
			gem.velocity = pull_dir * speed

func _on_area_weapon_hit(body: Node2D) -> void:
	if body is CharacterBody2D and body.is_in_group("enemies"):
		if body.has_method("take_damage"):
			body.take_damage(damage)

func _update_weapon_area() -> void:
	# Scale the area weapon radius
	var shape = weapon_area.get_node("CollisionShape2D").shape as CircleShape2D
	if shape:
		shape.radius = area_size
	var hitbox_shape = weapon_area.get_node("Hitbox/CollisionShape2D").shape as CircleShape2D
	if hitbox_shape:
		hitbox_shape.radius = area_size

func _update_hud() -> void:
	var hud = get_node("../HUD")
	if hud and hud.has_method("update_bars"):
		hud.update_bars(health, max_health, xp, xp_to_next_level)

func apply_upgrade(upgrade_type: String) -> void:
	match upgrade_type:
		"speed":
			speed += 20
		"max_health":
			max_health += 20
			health += 20
		"damage":
			damage += 5
		"attack_speed":
			attack_speed = maxf(0.2, attack_speed - 0.1)
		"projectile_count":
			projectile_count += 1
		"area_size":
			area_size += 15.0
			_update_weapon_area()
		"magnet":
			magnet_range += 30.0
		"regen":
			# Handled in game manager or via timer
			pass
	_update_hud()
