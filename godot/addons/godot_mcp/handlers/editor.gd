@tool
class_name MCPEditorHandlers
extends RefCounted
## Domain handler: editor.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter

# Two-phase capture state: the viewport read-back is deferred one rendered
# frame (get_image() inline can stall the router on some display servers —
# observed as a server-side timeout on macOS); callers poll until ready.
var _shot: Dictionary = {}
var _grab_queued := false
# #416/#456: frame-dependent handlers self-report why the editor isn't
# cooperating instead of stalling into the bridge's generic TIMEOUT. When the
# deferred grab hasn't landed for this many polls, report the reason so the
# server relays the actual cause (e.g. editor not redrawing) to the agent.
const _PENDING_GRACE_POLLS := 2
var _pending_polls := 0



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
	if not _shot.is_empty():
		var done := _shot
		_shot = {}
		_grab_queued = false
		_pending_polls = 0
		return _router._ok(done)
	var base_control := EditorInterface.get_base_control()
	if base_control == null:
		return _router._fail("INTERNAL_ERROR", "Editor base control is unavailable.")
	var tree := base_control.get_tree()
	if tree == null:
		return _router._fail("INTERNAL_ERROR", "Editor scene tree is unavailable.")
	if not _grab_queued:
		tree.process_frame.connect(_grab_screenshot.bind(base_control), ConnectFlags.CONNECT_ONE_SHOT)
		_grab_queued = true
		# Qodo #457 round-2: the counter is shared across concurrent capture
		# invocations; reset it whenever a NEW grab is queued so a prior
		# invocation's polls can't shorten this one's grace window.
		_pending_polls = 0
	_pending_polls += 1
	if _pending_polls > _PENDING_GRACE_POLLS:
		# #416/#456: the grab stays pending across multiple rendered frames — the
		# editor isn't redrawing (occluded/minimized). Say so instead of letting
		# the poller starve into the bridge's generic timeout text.
		return _router._ok({
			"ready": false,
			"pending": true,
			"reason": "editor_not_drawing",
		})
	return _router._ok({"ready": false})


func _grab_screenshot(base_control: Control) -> void:
	var viewport := base_control.get_viewport()
	if viewport == null:
		_shot = {"ready": true, "error": "Editor viewport is unavailable."}
		return
	var texture := viewport.get_texture()
	if texture == null:
		_shot = {"ready": true, "error": "No viewport texture (no rendered frame)."}
		return
	var image := texture.get_image()
	if image == null or image.is_empty():
		_shot = {"ready": true, "error": "Could not capture the editor viewport image."}
		return
	_shot = _encode_png(image)
	_shot["ready"] = true


