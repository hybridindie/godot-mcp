@tool
class_name MCPProjectFSHandlers
extends RefCounted
const Coerce := preload("../type_coerce.gd")
const Remap := preload("../mcp_fs_remap.gd")
## Domain handler: project fs.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter





func _file_contains(path: String, needle: String) -> bool:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return false
	if file.get_length() > 2_000_000:  # skip large/binary files
		file.close()
		return false
	var text := file.get_as_text()
	file.close()
	return text.contains(needle)


func _search(dir_path: String, name_glob: String, content: String, max_results: int, out: Array) -> bool:
	var dir := DirAccess.open(dir_path)
	if dir == null:
		return false
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if not name.begins_with("."):
			var full := dir_path.path_join(name)
			if dir.current_is_dir():
				if _search(full, name_glob, content, max_results, out):
					dir.list_dir_end()
					return true
			elif (name_glob.is_empty() or name.match(name_glob)) \
					and (content.is_empty() or _file_contains(full, content)):
				out.append(full)
				if out.size() >= max_results:
					dir.list_dir_end()
					return true
		name = dir.get_next()
	dir.list_dir_end()
	return false


func _fs_node(dir_path: String, max_depth: int) -> Dictionary:
	var node: Dictionary = {
		"name": ("res://" if dir_path == "res://" else dir_path.trim_suffix("/").get_file()),
		"path": dir_path,
		"type": "directory",
		"children": [],
	}
	if max_depth == 0:
		return node
	var dir := DirAccess.open(dir_path)
	if dir == null:
		return node
	var child_depth: int = (max_depth - 1) if max_depth > 0 else -1
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if not name.begins_with("."):
			var full := dir_path.path_join(name)
			if dir.current_is_dir():
				node["children"].append(_fs_node(full, child_depth))
			else:
				node["children"].append({"name": name, "path": full, "type": "file"})
		name = dir.get_next()
	dir.list_dir_end()
	return node


## Recursively collect files matching name_glob and/or content; returns true if the
## result was truncated at max_results.
func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_get_filesystem_tree"] = _cmd_get_filesystem_tree
	handlers["cmd_get_setting"] = _cmd_get_setting
	handlers["cmd_path_to_uid"] = _cmd_path_to_uid
	handlers["cmd_search_files"] = _cmd_search_files
	handlers["cmd_set_setting"] = _cmd_set_setting
	handlers["cmd_uid_to_path"] = _cmd_uid_to_path
	handlers["cmd_delete_resource_file"] = _cmd_delete_resource_file
	handlers["cmd_move_resource_file"] = _cmd_move_resource_file


# -- handlers ----------------------------------------------------------------

func _cmd_get_filesystem_tree(params: Dictionary) -> Dictionary:
	var directory := str(params.get("directory", "res://"))
	if not directory.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "directory must be inside the project (res://…).")
	if not DirAccess.dir_exists_absolute(directory):
		return _router._fail("RESOURCE_NOT_FOUND", "No directory '%s'." % directory)
	var max_depth := int(params.get("max_depth", -1))
	return _router._ok({"tree": _fs_node(directory, max_depth)})



func _cmd_search_files(params: Dictionary) -> Dictionary:
	var directory := str(params.get("directory", "res://"))
	if not directory.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "directory must be inside the project (res://…).")
	if not DirAccess.dir_exists_absolute(directory):
		return _router._fail("RESOURCE_NOT_FOUND", "No directory '%s'." % directory)
	var name_glob := str(params.get("name_glob", ""))
	var content := str(params.get("content", ""))
	var max_results := int(params.get("max_results", 200))
	var matches: Array = []
	var truncated := _search(directory, name_glob, content, max_results, matches)
	return _router._ok({"matches": matches, "truncated": truncated})



func _cmd_get_setting(params: Dictionary) -> Dictionary:
	var setting := str(params.get("name", ""))
	if not ProjectSettings.has_setting(setting):
		return _router._ok({"name": setting, "value": null, "exists": false})
	return _router._ok({
		"name": setting,
		"value": Coerce.to_json(ProjectSettings.get_setting(setting)),
		"exists": true,
	})



func _cmd_set_setting(params: Dictionary) -> Dictionary:
	var setting := str(params.get("name", ""))
	if setting.is_empty():
		return _router._fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	var refusal := _unknown_setting_refusal(setting)
	if not refusal.is_empty():
		return _router._fail("VALIDATION_ERROR", refusal)
	var raw: Variant = params.get("value")
	var value: Variant = raw
	if ProjectSettings.has_setting(setting):
		# Coerce to the setting's existing type so e.g. a vector dict becomes a Vector2.
		value = Coerce.from_json(raw, typeof(ProjectSettings.get_setting(setting)))
	ProjectSettings.set_setting(setting, value)
	ProjectSettings.save()
	return _router._ok({
		"name": setting,
		"value": Coerce.to_json(ProjectSettings.get_setting(setting)),
		"set": true,
	})


## Refusal text for an obvious typo'd ProjectSettings key, or "" when the write
## is allowed (issue #462).
##
## Godot silently persists any key you set — a typo like
## `application/config/main_scene` (the real key is `application/run/main_scene`)
## is written to project.godot, never read, and never errors. The engine's own
## known-key set is the singleton's property list (#425-adjacent: same list the
## Inspector shows). A hard refusal must only fire when we can be sure the key
## is dead, so the gate is:
##   - key is already set / in the known list → allowed (round-trip keys like
##     `config_version` are not all in the list but are real),
##   - key under a user-owned namespace (autoload, custom, or a section the
##     engine does not declare, e.g. a game's own `my_game/…`) → allowed —
##     Godot documents custom sections as a supported pattern,
##   - otherwise (typo inside a known engine section) → refuse with a hint
##     suggesting the closest real key.
func _unknown_setting_refusal(setting: String) -> String:
	if ProjectSettings.has_setting(setting):
		return ""
	var known: Array = []
	for p in ProjectSettings.get_property_list():
		known.append(str(p.get("name", "")))
	if known.has(setting):
		return ""
	var slash := setting.find("/")
	if slash <= 0:
		# No section (or root special keys like config_version): engine accepts these.
		return ""
	var section := setting.substr(0, slash)
	if not _KNOWN_SECTIONS.has(section):
		return ""
	var suggestion := _closest_known_key(setting, known)
	var hint := "Unknown ProjectSettings key '%s'. Godot would write it to project.godot but never read it." % setting
	if not suggestion.is_empty():
		hint += " Did you mean '%s'?" % suggestion
	return hint


const _KNOWN_SECTIONS := {
	"application": true,
	"accessibility": true,
	"audio": true,
	"collada": true,
	"compression": true,
	"debug": true,
	"display": true,
	"editor": true,
	"editor_plugins": true,
	"filesystem": true,
	"gui": true,
	"input": true,
	"input_devices": true,
	"internationalization": true,
	"layer_names": true,
	"memory": true,
	"navigation": true,
	"network": true,
	"physics": true,
	"rendering": true,
	"threading": true,
	"xr": true,
}


## Nearest known key by shared prefix depth — surfaces `application/run/main_scene`
## for the `application/config/main_scene` typo without pulling in a full
## edit-distance implementation.
func _closest_known_key(setting: String, known: Array) -> String:
	var parts := setting.split("/")
	var best := ""
	var best_score := 0
	for candidate in known:
		var c_parts: PackedStringArray = str(candidate).split("/")
		var score := 0
		for i in range(mini(parts.size(), c_parts.size())):
			if parts[i] != c_parts[i]:
				break
			score += 1
		if score > best_score:
			best_score = score
			best = str(candidate)
	return best



func _cmd_path_to_uid(params: Dictionary) -> Dictionary:
	var path := str(params.get("path", ""))
	var id := ResourceLoader.get_resource_uid(path)
	if id == -1:
		return _router._fail("RESOURCE_NOT_FOUND", "No UID for '%s'." % path)
	return _router._ok({"path": path, "uid": ResourceUID.id_to_text(id)})



func _cmd_uid_to_path(params: Dictionary) -> Dictionary:
	var uid := str(params.get("uid", ""))
	var id := ResourceUID.text_to_id(uid)
	if id == -1 or not ResourceUID.has_id(id):
		return _router._fail("RESOURCE_NOT_FOUND", "Unknown UID '%s'." % uid)
	return _router._ok({"uid": uid, "path": ResourceUID.get_id_path(id)})


## Delete a res:// file and its .uid sidecar — the inverse of the file-creating
## handlers (issue #217). res:// containment is enforced server-side; the check here
## is defense-in-depth. Undoable: the file (and uid) bytes are captured first and
## restored on undo, so binary resources round-trip exactly.
## A deleted *scene* that is open in the editor also gets its tab closed (issue
## #422): the stale in-memory copy would otherwise linger and a later
## create_scene at the same path resurrects mangled duplicate nodes.
func _cmd_delete_resource_file(params: Dictionary) -> Dictionary:
	var path := str(params.get("path", ""))
	if not path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "path must be a res:// file.")
	if not FileAccess.file_exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No file at '%s'." % path)
	var bytes := FileAccess.get_file_as_bytes(path)
	var uid_path := path + ".uid"
	var had_uid := FileAccess.file_exists(uid_path)
	var uid_bytes := FileAccess.get_file_as_bytes(uid_path) if had_uid else PackedByteArray()
	# Close the scene tab BEFORE the undoable delete so the editor forgets the
	# in-memory scene; open tabs of .tscn/.scn files are the resurrection trap.
	# close_scene() only closes the ACTIVE tab (Godot 4.7 EditorInterface has no
	# close-by-path), so when the target is open but not active we must activate
	# it first (open_scene_from_path re-activates an already-open tab) and verify
	# the switch landed before closing — otherwise we'd close the wrong tab and
	# discard unsaved work in an unrelated scene.
	var tab_closed := false
	if path.ends_with(".tscn") or path.ends_with(".scn"):
		for open_path in EditorInterface.get_open_scenes():
			if open_path != path:
				continue
			var active_root := EditorInterface.get_edited_scene_root()
			if active_root == null or active_root.scene_file_path != path:
				EditorInterface.open_scene_from_path(path)
				active_root = EditorInterface.get_edited_scene_root()
				if active_root == null or active_root.scene_file_path != path:
					break  # activation failed — refuse to guess which tab is active
			tab_closed = EditorInterface.close_scene() == OK
			break
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Delete file %s" % path)
	ur.add_do_method(_router, "_remove_file_with_uid", path)
	ur.add_undo_method(_router, "_write_file_bytes", path, bytes)
	if had_uid:
		ur.add_undo_method(_router, "_write_file_bytes", uid_path, uid_bytes)
	ur.commit_action()
	EditorInterface.get_resource_filesystem().update_file(path)
	return _router._ok({"path": path, "deleted": true, "had_uid": had_uid, "tab_closed": tab_closed})


## Move/rename a res:// file and rewrite every referencing file (issue #532).
##
## res:// containment is enforced server-side; the checks here are
## defense-in-depth + the three #532 refusals: missing source, existing
## destination, and an open-and-unsaved scene (the in-memory copy would clobber
## the moved file — hint points at save_scene first).
##
## The editor's own move dialog does its remap in C++ (FileSystemDock::_move);
## GDScript has no move-with-remap API, so the mover implements the equivalent:
## DirAccess.rename_absolute for the file (+ its .uid sidecar), then a
## project-wide text remap of both path-form ("res://old.gd") and uid-form
## ("uid://…") references across text-editable project files (.tscn/.scn/.gd/
## .tres/.import/.cfg/.cs). ResourceUID.set_id re-points the moved file's uid at
## its new path, and the filesystem is scanned so instances/imports follow.
## NOT UndoRedo-tracked (undoable=false always, with a recovery hint) — reverse
## it with a second move or version control. The `preview` flag (the dry-run)
## runs the same refusals + reports the files that WOULD change, mutating nothing.
func _cmd_move_resource_file(params: Dictionary) -> Dictionary:
	var path := str(params.get("path", ""))
	var new_path := str(params.get("new_path", ""))
	if path.is_empty() or new_path.is_empty():
		return _router._fail("VALIDATION_ERROR", "'path' and 'new_path' are required.")
	# Defense-in-depth containment (server validates first, #205/#217).
	for candidate: String in [path, new_path]:
		if Remap.escapes_res_root(candidate) and not candidate.begins_with("res://"):
			return _router._fail("VALIDATION_ERROR", "%s must be a res:// path." % candidate, "path")
		if Remap.escapes_res_root(candidate):
			return _router._fail(
				"VALIDATION_ERROR",
				"Path escapes the project root (res://). Got: '%s'" % candidate,
				"new_path" if candidate == new_path else "path",
			)
	if path == new_path:
		return _router._fail("VALIDATION_ERROR", "'new_path' must differ from 'path'.")
	if not FileAccess.file_exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No file at '%s'." % path, "path")
	if FileAccess.file_exists(new_path):
		return _router._fail(
			"VALIDATION_ERROR",
			"A file already exists at '%s'. Move elsewhere (or delete the existing file first)." % new_path,
			"new_path",
		)
	# #532 refusal: moving an open scene with unsaved changes would clobber the
	# in-memory copy (the editor holds the buffer under the OLD path; after the
	# move the save writes the old content back to the OLD path and the moved
	# file diverges). get_unsaved_scenes() (4.4+) lists them by path.
	if (path.ends_with(".tscn") or path.ends_with(".scn")) \
			and path in EditorInterface.get_unsaved_scenes():
		return _router._fail(
			"PRECONDITION_FAILED",
			"'%s' is open and has unsaved changes — moving it now would clobber the in-memory copy. Call save_scene first, then move." % path,
			"scene_saved",
		)
	var uid := ResourceLoader.get_resource_uid(path)
	var uid_text := ResourceUID.id_to_text(uid) if uid != -1 else ""
	# The referencing files: a project-wide search for the old path (and the
	# uid form) across text-editable project files. Mirrors search_files.
	var referencing := Remap.find_referencing_files(path, uid_text)
	var remaps: Array = []
	if params.get("preview", false):
		# The dry-run preview: report the files that WOULD change (the count a
		# rewrite would produce), mutating nothing.
		for file: String in referencing:
			var count := FileAccess.get_file_as_string(file).count(path)
			if count > 0:
				remaps.append({"file": file, "count": count})
	else:
		remaps = Remap.rewrite_references(path, new_path, referencing, _router._write_file_text)
		# Move the file + its .uid sidecar.
		var moved := DirAccess.rename_absolute(
			ProjectSettings.globalize_path(path), ProjectSettings.globalize_path(new_path)
		)
		if moved != OK:
			return _router._fail("INTERNAL_ERROR", "Failed to move '%s' to '%s' (error %d)." % [path, new_path, moved])
		var uid_path := path + ".uid"
		if FileAccess.file_exists(uid_path):
			DirAccess.rename_absolute(
				ProjectSettings.globalize_path(uid_path),
				ProjectSettings.globalize_path(new_path + ".uid"),
			)
		# Re-point the uid at the new location so uid:// references resolve.
		if uid != -1:
			ResourceUID.set_id(uid, new_path)
		var fs := EditorInterface.get_resource_filesystem()
		fs.update_file(path)  # drops the stale entry
		fs.update_file(new_path)
		fs.scan()
	return _router._ok({
		"old_path": path,
		"new_path": new_path,
		"updated_refs": remaps,
		"moved": not params.get("preview", false),
		# Honest reporting (issue #532): a file move is not UndoRedo-tracked —
		# reverse it with a second move or version control.
		"undoable": false,
		"hint": "A file move is not UndoRedo-tracked; reverse it with a second move_file(old→new) or version control.",
	})


