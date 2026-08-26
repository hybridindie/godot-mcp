extends CharacterBody2D

const SPEED := 250.0
var health := 100.0
var max_health := 100.0
var xp := 0
var level := 1
var xp_to_next := 5
var damage_cooldown := 0.0

signal health_changed(hp: float, max_hp: float)
signal xp_changed(xp: int, level: int, to_next: int)
signal died

func _ready() -> void:
	add_to_group("player")
	update_ui()

func _physics_process(delta: float) -> void:
	var gm := get_node_or_null("/root/GameManager")
	if gm and gm.state != 1:  # not PLAYING
		return
	var input_dir := Input.get_vector("move_left", "move_right", "move_up", "move_down")
	velocity = input_dir * SPEED
	move_and_slide()
	damage_cooldown = max(0.0, damage_cooldown - delta)
	if damage_cooldown <= 0.0:
		for i in get_slide_collision_count():
			var col := get_slide_collision(i)
			var collider: Node = col.get_collider()
			if collider and collider.is_in_group("enemies"):
				take_damage(collider.damage)
				damage_cooldown = 0.5
				break

func take_damage(amount: float) -> void:
	health = max(0.0, health - amount)
	health_changed.emit(health, max_health)
	if health <= 0.0:
		var gm := get_node_or_null("/root/GameManager")
		if gm:
			gm.end_game()
		died.emit()

func gain_xp(amount: int) -> void:
	xp += amount
	while xp >= xp_to_next:
		xp -= xp_to_next
		level += 1
		xp_to_next = int(xp_to_next * 1.5)
		max_health += 10.0
		health = min(max_health, health + 20.0)
	xp_changed.emit(xp, level, xp_to_next)

func update_ui() -> void:
	health_changed.emit(health, max_health)
	xp_changed.emit(xp, level, xp_to_next)