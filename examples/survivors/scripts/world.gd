extends Node2D

const TILE_SIZE := 64
const GRID_RADIUS := 20
const OBSTACLE_COUNT := 40
const OBSTACLE_MIN_SIZE := 32
const OBSTACLE_MAX_SIZE := 96

func _ready() -> void:
	_draw_background()
	_place_obstacles()

func _draw_background() -> void:
	for x in range(-GRID_RADIUS, GRID_RADIUS):
		for y in range(-GRID_RADIUS, GRID_RADIUS):
			var tile := Polygon2D.new()
			var s := float(TILE_SIZE)
			tile.polygon = PackedVector2Array([
				Vector2(0, 0), Vector2(s, 0), Vector2(s, s), Vector2(0, s)
			])
			tile.position = Vector2(x * TILE_SIZE, y * TILE_SIZE)
			var dark := (x + y) % 2 == 0
			if dark:
				tile.color = Color(0.10, 0.12, 0.16, 1.0)
			else:
				tile.color = Color(0.14, 0.16, 0.20, 1.0)
			$Background.add_child(tile)

func _place_obstacles() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = hash("survivors_obstacles")
	for i in range(OBSTACLE_COUNT):
		var pos := Vector2.ZERO
		for _try in range(20):
			pos = Vector2(
				rng.randf_range(-GRID_RADIUS * TILE_SIZE, GRID_RADIUS * TILE_SIZE),
				rng.randf_range(-GRID_RADIUS * TILE_SIZE, GRID_RADIUS * TILE_SIZE)
			)
			if pos.length() > 200.0:
				break
		var w := float(rng.randi_range(OBSTACLE_MIN_SIZE, OBSTACLE_MAX_SIZE))
		var h := float(rng.randi_range(OBSTACLE_MIN_SIZE, OBSTACLE_MAX_SIZE))
		var body := StaticBody2D.new()
		body.position = pos
		body.collision_layer = 16
		body.collision_mask = 0
		var poly := Polygon2D.new()
		poly.polygon = PackedVector2Array([
			Vector2(-w / 2.0, -h / 2.0), Vector2(w / 2.0, -h / 2.0),
			Vector2(w / 2.0, h / 2.0), Vector2(-w / 2.0, h / 2.0)
		])
		var shade := rng.randf_range(0.25, 0.45)
		poly.color = Color(shade, shade * 0.8, shade * 0.6, 1.0)
		body.add_child(poly)
		var col := CollisionShape2D.new()
		var shape := RectangleShape2D.new()
		shape.size = Vector2(w, h)
		col.shape = shape
		body.add_child(col)
		$Obstacles.add_child(body)