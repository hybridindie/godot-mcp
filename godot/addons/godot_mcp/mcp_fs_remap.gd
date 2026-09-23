@tool
class_name MCPFsRemap
extends RefCounted
## Pure, read-only helpers for project-file moves (issue #532).
##
## These helpers take paths (never EditorInterface), so they are verifiable
## headlessly (see godot/tests/move_file_smoke.gd). All output is JSON-safe.
## The cmd_move_resource_file handler supplies the write callback and the
## editor glue (filesystem scan, ResourceUID re-point, unsaved-scene refusal).

## The text file kinds a reference may live in (code, scenes, resources,
## imports, project config). Binary/asset files are skipped by read caps in
## the discovery walk.
const TEXT_EXTENSIONS := [
	".gd", ".cs", ".tscn", ".scn", ".tres", ".import", ".cfg", ".shader", ".gdshader",
]


static func is_text_resource(path: String) -> bool:
	for ext in TEXT_EXTENSIONS:
		if path.ends_with(ext):
			return true
	return false


## True when `path` escapes the res:// project root (path traversal) — the
## GDScript mirror of the server-side posixpath containment check (#205/#217).
static func escapes_res_root(path: String) -> bool:
	if not path.begins_with("res://"):
		return true
	var norm := path.substr(6).replace("\\", "/")
	return norm == ".." or norm.begins_with("../") or norm.begins_with("/")


## Project-wide walk collecting text files that reference `path` (path-form)
## or `uid_text` (uid-form, when non-empty). Skips hidden dirs (.godot, .git)
## like the search walk. Excludes the moved file itself.
static func find_referencing_files(path: String, uid_text: String) -> Array:
	var matches: Array = []
	_collect_references("res://", path, uid_text, matches)
	return matches


static func _collect_references(
	dir_path: String, path: String, uid_text: String, out: Array
) -> void:
	var dir := DirAccess.open(dir_path)
	if dir == null:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if not name.begins_with("."):
			var full := dir_path.path_join(name)
			if dir.current_is_dir():
				_collect_references(full, path, uid_text, out)
			elif is_text_resource(full) and full != path:
				var text := FileAccess.get_file_as_string(full)
				if text.contains(path) or (uid_text != "" and text.contains(uid_text)):
					out.append(full)
		name = dir.get_next()
	# Pair list_dir_end with list_dir_begin: without it the DirAccess handle
	# leaks, and enough recursion levels exhaust the engine's open-dir handles
	# so later opens return null and the walk silently finds nothing.
	dir.list_dir_end()


## Rewrite every path-form reference to `path` inside each file in `files`;
## returns [{file, count}] for the files actually changed. The uid reference
## string itself never changes (the uid re-points at the new path via
## ResourceUID.set_id) — only path-form references are rewritten. `writer` is
## the caller's (path, text) callback — the router's filesystem-updating writer.
static func rewrite_references(path: String, new_path: String, files: Array, writer: Callable) -> Array:
	var updated: Array = []
	for file: String in files:
		var text := FileAccess.get_file_as_string(file)
		var count := text.count(path)
		if count == 0:
			continue
		writer.call(file, text.replace(path, new_path))
		updated.append({"file": file, "count": count})
	return updated