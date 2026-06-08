extends Node
## Enemy spawner with wave-based difficulty scaling.

@export var enemy_scene: PackedScene = preload("res://scenes/enemy.tscn")
@export var spawn_radius: float = 500.0
@export var min_spawn_radius: float = 400.0
@export var base_spawn_rate: float = 2.0
@export var max_enemies: int = 200

var player: Node2D
var wave: int = 1
var enemies_killed: int = 0
var spawn_timer: float = 0.0
var total_time: float = 0.0
var _last_wave_tick: int = 0

func _ready() -> void:
	player = get_node_or_null("../Player")

func _process(delta: float) -> void:
	total_time += delta
	spawn_timer -= delta
	
	if spawn_timer <= 0 and player != null and player.alive:
		_spawn_wave()
		spawn_timer = _get_spawn_rate()
	
	# Difficulty scaling every 30 seconds (guard against multiple triggers per second)
	var current_tick := int(total_time)
	if current_tick > 0 and current_tick % 30 == 0 and current_tick != _last_wave_tick:
		_last_wave_tick = current_tick
		_wave_increase()

func _spawn_wave() -> void:
	var enemy_count := get_tree().get_nodes_in_group("enemies").size()
	if enemy_count >= max_enemies:
		return
	
	var spawn_count := mini(_get_spawn_count(), max_enemies - enemy_count)
	
	for i in spawn_count:
		var enemy = enemy_scene.instantiate()
		
		# Clamp spawn ring to arena bounds
		var arena := get_node_or_null("../Background")
		var half := Vector2(1024, 768)
		if arena and arena.has_method("_spawn_walls"):
			half = arena.arena_half_size
		var margin := 24.0  # keep enemy collision body inside arena
		
		# Spawn at random angle outside min_spawn_radius
		var angle := randf() * TAU
		var dist := min_spawn_radius + randf() * (spawn_radius - min_spawn_radius)
		var spawn_pos := player.global_position + Vector2(cos(angle), sin(angle)) * dist
		
		# Clamp to arena
		spawn_pos.x = clampf(spawn_pos.x, -half.x + margin, half.x - margin)
		spawn_pos.y = clampf(spawn_pos.y, -half.y + margin, half.y - margin)
		
		enemy.global_position = spawn_pos
		
		get_parent().add_child.call_deferred(enemy)
		
		# Scale enemy stats with wave (after adding to tree so _ready has run)
		if enemy.has_method("take_damage"):
			enemy.max_health = int(enemy.max_health * (1.0 + wave * 0.2))
			enemy.health = enemy.max_health
			enemy.speed = enemy.speed * (1.0 + wave * 0.05)
			enemy.xp_value = enemy.xp_value + wave * 2

func _get_spawn_rate() -> float:
	# Decrease spawn interval as waves progress
	return maxf(0.3, base_spawn_rate - wave * 0.1)

func _get_spawn_count() -> int:
	# Increase spawn count with waves
	return 1 + int(wave * 0.5)

func _wave_increase() -> void:
	wave += 1
	GameManager.update_wave(wave)

func get_wave() -> int:
	return wave

func get_time() -> float:
	return total_time
