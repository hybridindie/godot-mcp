@tool
class_name MCPEditorHandlers
extends RefCounted
## Domain handler: editor.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter



func _encode_png(image: Image) -> Dictionary:
	return {
		"format": "png",
		"width": image.get_width(),
		"height": image.get_height(),
		"base64": Marshalls.raw_to_base64(image.save_png_to_buffer()),
	}


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_capture_editor_screenshot"] = _cmd_capture_editor_screenshot


# -- handlers ----------------------------------------------------------------

func _cmd_capture_editor_screenshot(_params: Dictionary) -> Dictionary:
	# Split the chain so any null intermediate returns a structured error, never crashes.
	var base_control := EditorInterface.get_base_control()
	if base_control == null:
		return _router._fail("INTERNAL_ERROR", "Editor base control is unavailable.")
	var viewport := base_control.get_viewport()
	if viewport == null:
		return _router._fail("INTERNAL_ERROR", "Editor viewport is unavailable.")
	var texture := viewport.get_texture()
	if texture == null:
		return _router._fail("INTERNAL_ERROR", "No viewport texture (no rendered frame; is a display available?).")
	var image := texture.get_image()
	if image == null:
		return _router._fail("INTERNAL_ERROR", "Could not capture the editor viewport image.")
	var result := _router._encode_png(image)
	if str(result.get("base64", "")).is_empty():
		return _router._fail("INTERNAL_ERROR", "PNG encoding produced no data.")
	return _router._ok(result)


