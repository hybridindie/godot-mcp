@tool
extends SceneTree
## Headless behavior test for the resilient import rescan (issue #628).
##
## Run via: godot --headless --path godot/ --script res://tests/import_rescan_smoke.gd
## Pins MCPImportAssetHandlers.ensure_scan against a fake filesystem: a scan is
## started when none is in flight, and deferred (never stacked) when one already is
## — the coalescing bug that let a freshly copied file sit unimported. Prints
## IMPORT_RESCAN_OK and quits 0 on success; prints each failure and
## IMPORT_RESCAN_FAIL, quits 1 otherwise. Wired into pytest by
## tests/integration/test_addon_import_rescan.py.

## A duck-typed stand-in for EditorFileSystem ({is_scanning, scan}).
class _FakeFS:
	var scanning := false
	var scans := 0

	func is_scanning() -> bool:
		return scanning

	func scan() -> void:
		scans += 1


func _initialize() -> void:
	var failures: Array[String] = []

	# No scan in flight → start one now.
	var idle := _FakeFS.new()
	if MCPImportAssetHandlers.ensure_scan(idle) != true:
		failures.append("ensure_scan should start a scan when idle")
	if idle.scans != 1:
		failures.append("expected exactly 1 scan when idle, got %d" % idle.scans)

	# A scan is already in flight → defer (do NOT stack a second scan).
	var busy := _FakeFS.new()
	busy.scanning = true
	if MCPImportAssetHandlers.ensure_scan(busy) != false:
		failures.append("ensure_scan should defer while a scan is in flight")
	if busy.scans != 0:
		failures.append("a stacked scan was issued while one was in flight (%d)" % busy.scans)

	# A missing filesystem is a safe no-op.
	if MCPImportAssetHandlers.ensure_scan(null) != false:
		failures.append("ensure_scan(null) should be false")

	if failures.is_empty():
		print("IMPORT_RESCAN_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("IMPORT_RESCAN_FAIL")
		quit(1)
