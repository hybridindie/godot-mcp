extends Node2D
## Infinite checkerboard background with a bounded arena.
## Arena is centered at origin and bounded by StaticBody2D walls.

@export var tile_size: int = 64
@export var arena_half_size: Vector2 = Vector2(1024, 768)
@export var color1: Color = Color(0.13, 0.55, 0.13, 1)
@export var color2: Color = Color(0.18, 0.65, 0.18, 1)
@export var wall_color: Color = Color(0.45, 0.35, 0.25, 1)
@export var wall_thickness: float = 64.0

func _ready() -> void:
	_spawn_walls()

func _spawn_walls() -> void:
	var half := arena_half_size
	var t := wall_thickness
	var h := t * 0.5
	# Top wall
	_add_wall(Vector2(0, -half.y - h), Vector2(half.x * 2 + t, t))
	# Bottom wall
	_add_wall(Vector2(0, half.y + h), Vector2(half.x * 2 + t, t))
	# Left wall
	_add_wall(Vector2(-half.x - h, 0), Vector2(t, half.y * 2 + t))
	# Right wall
	_add_wall(Vector2(half.x + h, 0), Vector2(t, half.y * 2 + t))

func _add_wall(center: Vector2, size: Vector2) -> void:
	var body := StaticBody2D.new()
	body.position = center
	body.collision_layer = 1
	body.collision_mask = 0
	var shape := RectangleShape2D.new()
	shape.size = size
	var coll := CollisionShape2D.new()
	coll.shape = shape
	body.add_child(coll)
	add_child(body)

func _process(_delta: float) -> void:
	queue_redraw()

func _draw() -> void:
	var cam := get_viewport().get_camera_2d()
	if not cam:
		return

	# Viewport size in screen pixels; convert to world units using zoom
	var vp_screen := get_viewport_rect().size
	var vp_world := vp_screen / cam.zoom
	var cam_pos := cam.global_position

	# Add a generous margin so tiles don't flicker at viewport edges
	var margin := tile_size * 2.0

	var start_x := int(floor((cam_pos.x - vp_world.x * 0.5 - margin) / tile_size))
	var end_x   := int(ceil ((cam_pos.x + vp_world.x * 0.5 + margin) / tile_size))
	var start_y := int(floor((cam_pos.y - vp_world.y * 0.5 - margin) / tile_size))
	var end_y   := int(ceil ((cam_pos.y + vp_world.y * 0.5 + margin) / tile_size))

	for x in range(start_x, end_x + 1):
		for y in range(start_y, end_y + 1):
			var pos := Vector2(x * tile_size, y * tile_size)
			var col := color1 if (x + y) % 2 == 0 else color2
			draw_rect(Rect2(pos, Vector2(tile_size, tile_size)), col)

	var half := arena_half_size
	var t := wall_thickness
	# Top
	draw_rect(Rect2(Vector2(-half.x - t, -half.y - t), Vector2((half.x * 2) + t * 2, t)), wall_color)
	# Bottom
	draw_rect(Rect2(Vector2(-half.x - t, half.y), Vector2((half.x * 2) + t * 2, t)), wall_color)
	# Left
	draw_rect(Rect2(Vector2(-half.x - t, -half.y), Vector2(t, half.y * 2)), wall_color)
	# Right
	draw_rect(Rect2(Vector2(half.x, -half.y), Vector2(t, half.y * 2)), wall_color)
