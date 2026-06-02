@tool
extends SceneTree
## Headless test for the screenshot PNG-encode path (issue #33).
##
## --headless does not render, so the editor-viewport *capture* can't be tested
## here. This covers the part that can: encoding an Image to base64 PNG via
## save_png_to_buffer + Marshalls.raw_to_base64. Prints SCREENSHOT_B64:<base64>
## for the pytest wrapper to decode and validate as a real PNG.


func _initialize() -> void:
	var image := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	image.fill(Color(1, 0, 0, 1))
	var buffer := image.save_png_to_buffer()
	var encoded := Marshalls.raw_to_base64(buffer)
	if encoded.is_empty():
		printerr("FAIL: empty base64")
		print("SCREENSHOT_TEST_FAIL")
		quit(1)
		return
	print("SCREENSHOT_B64:%s" % encoded)
	print("SCREENSHOT_TEST_OK")
	quit(0)
