extends Node

const ENEMY_SCENE := preload("res://scenes/enemy.tscn")
const PROJECTILE_SCENE := preload("res://scenes/projectile.tscn")
const XP_GEM_SCENE := preload("res://scenes/xp_gem.tscn")

enum State { MENU, PLAYING, PAUSED, GAME_OVER }
var state: State = State.MENU

var spawn_timer := 0.0
var spawn_interval := 2.0
var wave := 1
var wave_timer := 0.0
var wave_duration := 30.0
var shoot_timer := 0.0
var shoot_interval := 0.5
var score := 0

signal state_changed(state: int)
signal score_changed(s: int)
signal wave_changed(w: int)

func _ready() -> void:
	_change_state(State.MENU)

func _get_world() -> Node2D:
	# Spawn entities under the main scene root (a Node2D) so Polygon2D renders.
	# The current scene is always a Node2D in this project.
	var scene: Node = get_tree().current_scene
	if scene is Node2D:
		return scene as Node2D
	return null

func _physics_process(delta: float) -> void:
	if state != State.PLAYING:
		return
	var player: Node2D = get_tree().get_first_node_in_group("player")
	if player == null:
		return
	var world: Node2D = _get_world()
	if world == null:
		return
	wave_timer += delta
	if wave_timer >= wave_duration:
		wave_timer = 0.0
		wave += 1
		spawn_interval = max(0.3, spawn_interval * 0.85)
		wave_changed.emit(wave)
	spawn_timer += delta
	if spawn_timer >= spawn_interval:
		spawn_timer = 0.0
		_spawn_enemy(player, world)
	shoot_timer += delta
	if shoot_timer >= shoot_interval:
		shoot_timer = 0.0
		_shoot(player, world)

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		if state == State.PLAYING:
			_change_state(State.PAUSED)
		elif state == State.PAUSED:
			_change_state(State.PLAYING)
	elif event.is_action_pressed("ui_accept"):
		if state == State.MENU:
			start_game()
		elif state == State.GAME_OVER:
			start_game()

func _change_state(new_state: State) -> void:
	state = new_state
	match state:
		State.MENU:
			get_tree().paused = false
		State.PLAYING:
			get_tree().paused = false
		State.PAUSED:
			get_tree().paused = true
		State.GAME_OVER:
			get_tree().paused = true
	state_changed.emit(state)

func _spawn_enemy(player: Node2D, world: Node2D) -> void:
	var angle := randf() * TAU
	var dist := 600.0
	var pos := player.global_position + Vector2.from_angle(angle) * dist
	var enemy := ENEMY_SCENE.instantiate()
	world.add_child(enemy)
	enemy.global_position = pos
	enemy.max_health = 30.0 + wave * 10.0
	enemy.health = enemy.max_health
	enemy.damage = 10.0 + wave * 2.0
	enemy.xp_value = 1
	enemy.enemy_died.connect(_on_enemy_died)

func _shoot(player: Node2D, world: Node2D) -> void:
	var nearest: Node2D = _find_nearest_enemy(player.global_position)
	if nearest == null:
		return
	var proj := PROJECTILE_SCENE.instantiate()
	world.add_child(proj)
	proj.global_position = player.global_position
	var dir: Vector2 = (nearest.global_position - player.global_position).normalized()
	proj.launch(dir)

func _find_nearest_enemy(pos: Vector2) -> Node2D:
	var best: Node2D = null
	var best_dist := 99999.0
	for enemy in get_tree().get_nodes_in_group("enemies"):
		var d := pos.distance_to(enemy.global_position)
		if d < best_dist:
			best_dist = d
			best = enemy
	return best

func _on_enemy_died(pos: Vector2, xp_val: int) -> void:
	score += 10
	score_changed.emit(score)
	var world: Node2D = _get_world()
	if world:
		var gem := XP_GEM_SCENE.instantiate()
		world.add_child(gem)
		gem.global_position = pos

func start_game() -> void:
	for e in get_tree().get_nodes_in_group("enemies"):
		e.queue_free()
	for g in get_tree().get_nodes_in_group("xp_gems"):
		g.queue_free()
	score = 0
	wave = 1
	spawn_timer = 0.0
	spawn_interval = 2.0
	wave_timer = 0.0
	shoot_timer = 0.0
	var player: Node2D = get_tree().get_first_node_in_group("player")
	if player:
		player.health = 100.0
		player.max_health = 100.0
		player.xp = 0
		player.level = 1
		player.xp_to_next = 5
		player.global_position = Vector2.ZERO
		player.update_ui()
	score_changed.emit(score)
	wave_changed.emit(wave)
	_change_state(State.PLAYING)

func end_game() -> void:
	_change_state(State.GAME_OVER)