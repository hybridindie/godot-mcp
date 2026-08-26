extends Node2D

const TILE_SIZE := 64
const OBSTACLE_COUNT := 40
const OBSTACLE_MIN_SIZE := 32
const OBSTACLE_MAX_SIZE := 96

var _view_radius_x := 12
var _view_radius_y := 12
var _tiles: Array[Polygon2D] = []
var _tile_count := 0
var _last_grid_x := 99999
var _last_grid_y := 99999

func _ready() -> void:
	_calc_view_radius()
	_init_tile_pool()
	_place_obstacles()

func _calc_view_radius() -> void:
	# Size the tile pool to cover the viewport plus a 2-tile margin.
	var vp := get_viewport().get_visible_rect().size
	var zoom := Vector2.ONE
	var cam := get_viewport().get_camera_2d()
	if cam:
		zoom = cam.zoom
	_view_radius_x = int(ceil((vp.x / zoom.x) / TILE_SIZE / 2.0)) + 2
	_view_radius_y = int(ceil((vp.y / zoom.y) / TILE_SIZE / 2.0)) + 2

func _init_tile_pool() -> void:
	_tile_count = (_view_radius_x * 2 + 1) * (_view_radius_y * 2 + 1)
	for i in range(_tile_count):
		var tile := Polygon2D.new()
		var s := float(TILE_SIZE)
		tile.polygon = PackedVector2Array([
			Vector2(0, 0), Vector2(s, 0), Vector2(s, s), Vector2(0, s)
		])
		$Background.add_child(tile)
		_tiles.append(tile)
	_update_tiles()

func _process(_delta: float) -> void:
	# Reposition tiles when the camera crosses a tile boundary
	var cam := _camera_pos()
	var gx := int(floor(cam.x / TILE_SIZE))
	var gy := int(floor(cam.y / TILE_SIZE))
	if gx != _last_grid_x or gy != _last_grid_y:
		_update_tiles(gx, gy)

func _camera_pos() -> Vector2:
	var cam := get_viewport().get_camera_2d()
	if cam:
		return cam.global_position
	return Vector2.ZERO

func _update_tiles(cx: int = 0, cy: int = 0) -> void:
	if cx == 0 and cy == 0:
		var cam := _camera_pos()
		cx = int(floor(cam.x / TILE_SIZE))
		cy = int(floor(cam.y / TILE_SIZE))
	_last_grid_x = cx
	_last_grid_y = cy
	var idx := 0
	for x in range(cx - _view_radius_x, cx + _view_radius_x + 1):
		for y in range(cy - _view_radius_y, cy + _view_radius_y + 1):
			if idx >= _tile_count:
				break
			var tile: Polygon2D = _tiles[idx]
			tile.position = Vector2(x * TILE_SIZE, y * TILE_SIZE)
			var dark := (x + y) % 2 == 0
			if dark:
				tile.color = Color(0.10, 0.12, 0.16, 1.0)
			else:
				tile.color = Color(0.14, 0.16, 0.20, 1.0)
			idx += 1

func _place_obstacles() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = hash("survivors_obstacles")
	for i in range(OBSTACLE_COUNT):
		var pos := Vector2.ZERO
		for _try in range(20):
			pos = Vector2(
				rng.randf_range(-2000.0, 2000.0),
				rng.randf_range(-2000.0, 2000.0)
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