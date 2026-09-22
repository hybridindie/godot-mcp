@tool
extends SceneTree
## Headless behavior test for the cached dock status-icon textures (issue #539).
##
## Run via: godot --headless --path godot/ --script res://tests/icon_cache_smoke.gd
## Verifies the status-icon cache: one texture per connection status, built
## lazily on first use, then reused BY IDENTITY on every status change (the hot
## path must not regenerate pixels). Also pins the dot's pixel behavior
## (opaque center in the status color, transparent outside the radius).
## Prints ICON_CACHE_TEST_OK, quits 0 on success.

const Icons := preload("res://addons/godot_mcp/mcp_status_icons.gd")

const Status := preload("res://addons/godot_mcp/mcp_bridge.gd").Status


func _initialize() -> void:
	var failures: Array[String] = []
	var icons: RefCounted = load("res://addons/godot_mcp/mcp_status_icons.gd").new()

	# First call per status builds lazily — three distinct textures.
	var disconnected: ImageTexture = icons.texture(Status.DISCONNECTED)
	var connecting: ImageTexture = icons.texture(Status.CONNECTING)
	var connected: ImageTexture = icons.texture(Status.CONNECTED)
	_ne(failures, "disconnected_vs_connecting", disconnected, connecting)
	_ne(failures, "connecting_vs_connected", connecting, connected)
	_ne(failures, "connected_vs_disconnected", connected, disconnected)
	if disconnected == null or connecting == null or connected == null:
		failures.append("lazy_build: every status should produce a texture")

	# Repeat calls return the SAME instance (reference swap, no regeneration).
	_eq(failures, "cache_identity_disc", icons.texture(Status.DISCONNECTED), disconnected)
	_eq(failures, "cache_identity_conn", icons.texture(Status.CONNECTING), connecting)
	_eq(failures, "cache_identity_conn2", icons.texture(Status.CONNECTED), connected)
	# The cache holds exactly the three statuses.
	_eq(failures, "cache_size", icons._textures.size(), 3)

	# Texture pixels: the dot is opaque at the center and transparent at the
	# corner, with the right color (behavior visually unchanged).
	var center: Color = connected.get_image().get_pixel(8, 8)
	_eq(failures, "dot_center_alpha", center.a, 1.0)
	# 8-bit RGBA quantization: 0.3 renders back as 0.298 (a wider-than-default
	# tolerance, since Color.is_equal_approx's 4-component epsilon is tighter
	# than the 1/255 step).
	if absf(center.r - 0.3) > 0.01 or absf(center.g - 0.8) > 0.01 or absf(center.b - 0.3) > 0.01:
		failures.append("dot_center_color: expected the green dot, got %s" % str(center))
	var corner: Color = connected.get_image().get_pixel(0, 0)
	_eq(failures, "corner_transparent", corner.a, 0.0)
	# Just outside the 6px radius is transparent.
	var outside: Color = connected.get_image().get_pixel(8, 1)
	_eq(failures, "outside_radius_transparent", outside.a, 0.0)

	# Unknown status falls back to gray and is also cached.
	var fallback: ImageTexture = icons.texture(-1)
	_eq(failures, "fallback_cached", icons.texture(-1), fallback)
	_eq(failures, "fallback_gray", fallback.get_image().get_pixel(8, 8), Color.GRAY)
	_eq(failures, "cache_size_after_fallback", icons._textures.size(), 4)

	if failures.is_empty():
		print("ICON_CACHE_TEST_OK")
		quit(0)
	else:
		push_error("ICON_CACHE_TEST_FAILURES: %s" % [str(failures)])
		quit(1)


func _eq(failures: Array[String], what: String, got: Variant, expected: Variant) -> void:
	if got != expected:
		failures.append("%s: expected %s, got %s" % [what, str(expected), str(got)])


func _ne(failures: Array[String], what: String, a: Variant, b: Variant) -> void:
	if a == b:
		failures.append("%s: expected distinct instances" % what)