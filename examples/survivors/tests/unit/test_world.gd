extends GutTest

# Tests for the world generator — infinite tile grid, obstacle count,
# obstacle collision layers, spawn area clearance, deterministic seeding.

var _main: Node2D


func before_each() -> void:
	var scene: PackedScene = load("res://scenes/main.tscn")
	_main = scene.instantiate() as Node2D
	add_child(_main)


func after_each() -> void:
	_main.free()


func test_background_has_tile_pool() -> void:
	# Tile pool size is computed from the viewport at _ready time.
	# In headless mode the viewport is small, so just verify it's non-empty
	# and matches the expected pool formula.
	var bg: Node = _main.get_node("Background")
	assert_not_null(bg, "Background node should exist")
	var count := bg.get_child_count()
	assert_gt(count, 0, "Tile pool should have tiles")
	# Pool = (rx*2+1) * (ry*2+1) — verify it's a perfect grid product
	var world: Node2D = _main
	var rx: int = world._view_radius_x
	var ry: int = world._view_radius_y
	assert_eq(count, (rx * 2 + 1) * (ry * 2 + 1), "Tile pool should match viewport-derived grid size")


func test_tiles_are_polygon2d() -> void:
	var bg: Node = _main.get_node("Background")
	var first: Node = bg.get_child(0)
	assert_eq(first.get_class(), "Polygon2D", "Background children should be Polygon2D tiles")


func test_tiles_use_two_colors() -> void:
	var bg: Node = _main.get_node("Background")
	var colors: Array = []
	for i in range(min(bg.get_child_count(), 100)):
		var poly: Polygon2D = bg.get_child(i) as Polygon2D
		if poly:
			var c: Color = poly.color
			if not colors.has(c):
				colors.append(c)
	assert_gte(colors.size(), 2, "Checkerboard should have at least 2 distinct colors")


func test_obstacles_count_matches_constant() -> void:
	var obstacles: Node = _main.get_node("Obstacles")
	assert_not_null(obstacles, "Obstacles node should exist")
	assert_eq(obstacles.get_child_count(), 40, "Should place exactly 40 obstacles")


func test_obstacles_are_static_bodies() -> void:
	var obstacles: Node = _main.get_node("Obstacles")
	for i in range(obstacles.get_child_count()):
		var child: Node = obstacles.get_child(i)
		assert_eq(child.get_class(), "StaticBody2D", "Obstacles should be StaticBody2D")


func test_obstacles_have_collision_layer_16() -> void:
	var obstacles: Node = _main.get_node("Obstacles")
	for i in range(obstacles.get_child_count()):
		var body: StaticBody2D = obstacles.get_child(i) as StaticBody2D
		assert_eq(body.collision_layer, 16, "Obstacles should be on layer 16 (bit 5)")


func test_obstacles_avoid_spawn_area() -> void:
	var obstacles: Node = _main.get_node("Obstacles")
	for i in range(obstacles.get_child_count()):
		var body: StaticBody2D = obstacles.get_child(i) as StaticBody2D
		var dist: float = body.global_position.length()
		assert_gte(dist, 200.0, "Obstacle %d at %v should be outside 200px spawn radius" % [i, body.global_position])


func test_obstacles_have_collision_shapes() -> void:
	var obstacles: Node = _main.get_node("Obstacles")
	for i in range(obstacles.get_child_count()):
		var body: StaticBody2D = obstacles.get_child(i) as StaticBody2D
		var has_col := false
		for child in body.get_children():
			if child is CollisionShape2D:
				has_col = true
				break
		assert_true(has_col, "Obstacle %d should have a CollisionShape2D" % i)


func test_obstacles_have_polygon2d_visuals() -> void:
	var obstacles: Node = _main.get_node("Obstacles")
	for i in range(obstacles.get_child_count()):
		var body: StaticBody2D = obstacles.get_child(i) as StaticBody2D
		var has_poly := false
		for child in body.get_children():
			if child is Polygon2D:
				has_poly = true
				break
		assert_true(has_poly, "Obstacle %d should have a Polygon2D visual" % i)


func test_obstacle_generation_is_deterministic() -> void:
	var scene: PackedScene = load("res://scenes/main.tscn")
	var main2: Node2D = scene.instantiate() as Node2D
	add_child(main2)
	var obs1: Node = _main.get_node("Obstacles")
	var obs2: Node = main2.get_node("Obstacles")
	assert_eq(obs1.get_child_count(), obs2.get_child_count(), "Same obstacle count on re-run")
	for i in range(obs1.get_child_count()):
		var p1: Vector2 = obs1.get_child(i).global_position
		var p2: Vector2 = obs2.get_child(i).global_position
		assert_eq(p1, p2, "Obstacle %d position should be deterministic (seeded)" % i)
	main2.free()