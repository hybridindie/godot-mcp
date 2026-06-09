@tool
class_name MCPImportAssetHandlers
extends RefCounted
const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")
## Domain handler: external asset import and material assembly (issue #108).
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_import_asset"] = _cmd_import_asset
	handlers["cmd_create_material_from_textures"] = _cmd_create_material_from_textures
	handlers["cmd_get_import_status"] = _cmd_get_import_status


# -- helpers -----------------------------------------------------------------

func _copy_file(source: String, target: String, overwrite: bool) -> int:
	if FileAccess.file_exists(target) and not overwrite:
		return ERR_ALREADY_EXISTS
	var src := FileAccess.open(source, FileAccess.READ)
	if src == null:
		return FileAccess.get_open_error()
	var dst := FileAccess.open(target, FileAccess.WRITE)
	if dst == null:
		src.close()
		return FileAccess.get_open_error()
	const CHUNK := 65536
	var remaining := src.get_length()
	while remaining > 0:
		var read_size := mini(CHUNK, remaining)
		var buf := src.get_buffer(read_size)
		dst.store_buffer(buf)
		remaining -= read_size
	src.close()
	dst.close()
	return OK


func _detect_type(path: String) -> String:
	var ext := path.get_extension().to_lower()
	match ext:
		"png", "jpg", "jpeg", "webp", "svg":
			return "Texture2D"
		"glb", "gltf", "fbx":
			return "PackedScene"
		"obj":
			return "Mesh"
		"wav":
			return "AudioStreamWAV"
		"ogg":
			return "AudioStreamOggVorbis"
		"mp3":
			return "AudioStreamMP3"
		"tres", "res":
			return "Resource"
		"tscn", "scn":
			return "PackedScene"
		"gd":
			return "GDScript"
		"cs":
			return "CSharpScript"
		"gdshader":
			return "Shader"
	return ""


# -- handlers ----------------------------------------------------------------

func _cmd_import_asset(params: Dictionary) -> Dictionary:
	var source := str(params.get("source", ""))
	var target_path := str(params.get("target_path", ""))
	var overwrite := bool(params.get("overwrite", false))
	var import_settings: Dictionary = params.get("import_settings", {})

	if not target_path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "target_path must start with res://.")

	var abs_target := ProjectSettings.globalize_path(target_path)
	var abs_source := source
	if source.begins_with("res://"):
		abs_source = ProjectSettings.globalize_path(source)

	var base_dir := abs_target.get_base_dir()
	if not DirAccess.dir_exists_absolute(base_dir):
		DirAccess.make_dir_recursive_absolute(base_dir)

	var err := _copy_file(abs_source, abs_target, overwrite)
	if err == ERR_ALREADY_EXISTS:
		return _router._fail("PRECONDITION_FAILED", "Target already exists. Pass overwrite=true to replace.", "overwrite")
	if err != OK:
		return _router._fail("INTERNAL_ERROR", "Failed to copy file (error %d)." % err)

	EditorInterface.get_resource_filesystem().scan()

	var detected_type := _detect_type(target_path)
	if import_settings.has("type"):
		detected_type = str(import_settings["type"])

	return _router._ok({
		"imported": true,
		"target_path": target_path,
		"detected_type": detected_type,
	})


func _cmd_create_material_from_textures(params: Dictionary) -> Dictionary:
	var path := str(params.get("path", ""))
	var channels: Dictionary = {
		"albedo": str(params.get("albedo", "")),
		"normal": str(params.get("normal", "")),
		"roughness": str(params.get("roughness", "")),
		"metallic": str(params.get("metallic", "")),
		"ao": str(params.get("ao", "")),
		"emission": str(params.get("emission", "")),
	}

	var material: StandardMaterial3D = StandardMaterial3D.new()
	var channels_set: Array = []

	for channel in channels:
		var tex_path: String = channels[channel]
		if tex_path.is_empty():
			continue
		if not ResourceLoader.exists(tex_path):
			return _router._fail("RESOURCE_NOT_FOUND", "Texture not found for '%s': '%s'." % [channel, tex_path])
		var tex: Texture2D = ResourceLoader.load(tex_path)
		if tex == null:
			return _router._fail("INTERNAL_ERROR", "Failed to load texture '%s' for '%s'." % [tex_path, channel])
		match channel:
			"albedo":
				material.albedo_texture = tex
			"normal":
				material.normal_texture = tex
			"roughness":
				material.roughness_texture = tex
			"metallic":
				material.metallic_texture = tex
			"ao":
				material.ao_texture = tex
			"emission":
				material.emission_texture = tex
		channels_set.append(channel)

	if path.is_empty():
		path = "res://materials/generated_%s.tres" % str(randi()).sha256_text().substr(0, 8)
	if not path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "path must start with res://.")

	var base_dir := path.get_base_dir()
	if not DirAccess.dir_exists_absolute(ProjectSettings.globalize_path(base_dir)):
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(base_dir))

	var err := ResourceSaver.save(material, path)
	if err != OK:
		return _router._fail("INTERNAL_ERROR", "Failed to save material to '%s' (error %d)." % [path, err])
	EditorInterface.get_resource_filesystem().update_file(path)

	return _router._ok({
		"material_path": path,
		"created": true,
		"channels_set": channels_set,
	})


func _cmd_get_import_status(params: Dictionary) -> Dictionary:
	var target_path := str(params.get("target_path", ""))
	if not target_path.begins_with("res://"):
		return _router._fail("VALIDATION_ERROR", "target_path must start with res://.")

	var import_file := ProjectSettings.globalize_path(target_path + ".import")
	var imported := FileAccess.file_exists(import_file)
	var last_modified: String = ""
	var type: String = ""

	if imported:
		var cfg := ConfigFile.new()
		var err := cfg.load(import_file)
		if err == OK:
			type = cfg.get_value("remap", "type", "")
		if type.is_empty():
			type = _detect_type(target_path)
		var mtime := FileAccess.get_modified_time(import_file)
		last_modified = Time.get_datetime_string_from_unix_time(mtime)
	else:
		# Fallback: the file may not have an .import sidecar yet; report
		# whether the actual resource file exists and the extension type.
		imported = ResourceLoader.exists(target_path)
		if imported:
			type = _detect_type(target_path)

	return _router._ok({
		"imported": imported,
		"last_modified": last_modified if not last_modified.is_empty() else null,
		"type": type if not type.is_empty() else null,
	})
