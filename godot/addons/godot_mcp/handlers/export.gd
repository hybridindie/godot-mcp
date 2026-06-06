@tool
class_name MCPExportHandlers
extends RefCounted
## Domain handler: export.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter




const _EXPORT_PRESETS_PATH := "res://export_presets.cfg"


func _read_export_presets() -> Dictionary:
	if not FileAccess.file_exists(_EXPORT_PRESETS_PATH):
		return {"has_config": false, "presets": []}
	var cfg := ConfigFile.new()
	if cfg.load(_EXPORT_PRESETS_PATH) != OK:
		return {"has_config": true, "presets": [], "error": "could not parse export_presets.cfg"}
	var presets: Array = []
	for section in cfg.get_sections():
		# preset.N holds a preset; preset.N.options holds its per-option values — skip those.
		if not section.begins_with("preset.") or section.ends_with(".options"):
			continue
		presets.append({
			"index": int(section.get_slice(".", 1)),
			"name": str(cfg.get_value(section, "name", "")),
			"platform": str(cfg.get_value(section, "platform", "")),
			"runnable": bool(cfg.get_value(section, "runnable", false)),
			"export_path": str(cfg.get_value(section, "export_path", "")),
		})
	presets.sort_custom(func(a, b): return a["index"] < b["index"])
	return {"has_config": true, "presets": presets}


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_get_export_info"] = _cmd_get_export_info
	handlers["cmd_list_export_presets"] = _cmd_list_export_presets


# -- handlers ----------------------------------------------------------------

func _cmd_list_export_presets(_params: Dictionary) -> Dictionary:
	var data := _router._read_export_presets()
	if data.has("error"):
		return _router._fail("INTERNAL_ERROR", str(data["error"]))
	return _router._ok(data)



func _cmd_get_export_info(_params: Dictionary) -> Dictionary:
	var data := _router._read_export_presets()
	if data.has("error"):
		return _router._fail("INTERNAL_ERROR", str(data["error"]))
	var names: Array = []
	for preset in data["presets"]:
		names.append(preset["name"])
	return _router._ok({
		"has_config": data["has_config"],
		"preset_count": (data["presets"] as Array).size(),
		"preset_names": names,
		"config_path": _EXPORT_PRESETS_PATH,
	})


