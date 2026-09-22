@tool
class_name MCPStatusIcons
extends RefCounted
## Cached connection-status icon textures (issue #539).
##
## The plugin entry's bottom-bar button used to regenerate a 16×16 dot texture
## pixel-by-pixel (256 `set_pixel` calls) on EVERY connection-status change —
## which fires on every reconnect-cycle tick. Three statuses → three immutable
## textures: this module builds each lazily on first use and returns the cached
## instance by identity afterwards, so the hot path is a reference swap with no
## allocation. Editor-free (Image/ImageTexture only) and headlessly verifiable
## (godot/tests/icon_cache_smoke.gd).

## MCPBridge.Status enum order (kept in sync with mcp_bridge.gd):
## DISCONNECTED, CONNECTING, CONNECTED.
const _STATUS_COLORS := {
	0: Color(0.9, 0.3, 0.3),
	1: Color(0.9, 0.7, 0.2),
	2: Color(0.3, 0.8, 0.3),
}

## One dot texture per status key (and any fallback key), built lazily.
var _textures: Dictionary = {}


## The cached texture for `status`; built lazily on first use. Unknown statuses
## fall back to gray and are cached too.
func texture(status: int) -> ImageTexture:
	var cached: ImageTexture = _textures.get(status)
	if cached != null:
		return cached
	var tex := _build_dot_texture(_STATUS_COLORS.get(status, Color.GRAY))
	_textures[status] = tex
	return tex


## Render one 16×16 colored-dot texture. The pixel-regeneration hot path #539
## removes — called once per status, not once per status change.
func _build_dot_texture(color: Color) -> ImageTexture:
	var size := 16
	var radius := 6.0
	var img := Image.create_empty(size, size, false, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 0))
	var center := Vector2(size / 2.0, size / 2.0)
	for x in range(size):
		for y in range(size):
			if Vector2(x, y).distance_to(center) <= radius:
				img.set_pixel(x, y, color)
	return ImageTexture.create_from_image(img)