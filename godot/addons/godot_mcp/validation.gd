@tool
class_name MCPValidation
extends RefCounted
## Project validation: built-in checks + project-registered validators (#758).
##
## Shared by the editor-side handler and the headless runner. A custom validator
## lives under `res://.mcp/validators/*.gd`, extends RefCounted, and implements
## `validate(context: Dictionary) -> Array[Dictionary]`; each finding carries
## `severity` (`error`/`warning`/`info`), `path`, and `message`. Invalid results
## are reported as findings, never silently dropped.

const VALIDATOR_DIR := "res://.mcp/validators"
const SKIP_DIRS := {".godot": true, ".git": true, ".import": true}


static func run(project_dir: String, include_warnings: bool = true) -> Dictionary:
	var findings: Array = []
	var validators: Array = []
	_check_autoloads(findings)
	_check_resource_dependencies(findings)
	_check_scripts(findings)
	_run_custom(project_dir, include_warnings, findings, validators)
	if not include_warnings:
		findings = findings.filter(
			func(f: Variant) -> bool: return str((f as Dictionary).get("severity", "error")) != "warning"
		)
	var valid := not findings.any(
		func(f: Variant) -> bool: return str((f as Dictionary).get("severity", "error")) == "error"
	)
	return {"valid": valid, "findings": findings, "validators": validators}


static func _file(path: String, message: String, severity: String = "error") -> Dictionary:
	return {"severity": severity, "path": path, "message": message}


static func _check_autoloads(findings: Array) -> void:
	for entry in ProjectSettings.get_property_list():
		var key := str(entry.get("name", ""))
		if not key.begins_with("autoload/"):
			continue
		var path := str(ProjectSettings.get_setting(key, "")).trim_prefix("*")
		if path.is_empty() or ResourceLoader.exists(path):
			continue
		findings.append(_file(
			path, "Autoload '%s' points at a missing resource." % key.trim_prefix("autoload/")
		))


static func _check_resource_dependencies(findings: Array) -> void:
	for path in _files("res://"):
		if not (path.ends_with(".tscn") or path.ends_with(".tres") or path.ends_with(".res")):
			continue
		for dep in ResourceLoader.get_dependencies(path):
			var dep_path := str(dep)
			if dep_path.begins_with("uid://"):
				var id := ResourceUID.text_to_id(dep_path)
				dep_path = ResourceUID.get_id_path(id) if id != -1 else ""
			if dep_path.begins_with("res://") and not FileAccess.file_exists(dep_path):
				findings.append(_file(path, "Missing dependency '%s'." % dep_path))


static func _check_scripts(findings: Array) -> void:
	for path in _files("res://"):
		if not path.ends_with(".gd") or path.contains("/addons/"):
			continue
		if ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_IGNORE) == null:
			findings.append(_file(path, "Script failed to load (parse error or missing dependency)."))


static func _run_custom(
	project_dir: String, include_warnings: bool, findings: Array, validators: Array
) -> void:
	if not DirAccess.dir_exists_absolute(VALIDATOR_DIR):
		return
	var names := DirAccess.get_files_at(VALIDATOR_DIR)
	if names.is_empty():
		return
	for name in names:
		if not str(name).ends_with(".gd"):
			continue
		var path := VALIDATOR_DIR.path_join(str(name))
		validators.append(path)
		var script: Variant = load(path)
		if script == null:
			findings.append(_file(path, "Validator failed to load."))
			continue
		var instance: Variant = script.new()
		if instance == null or not instance.has_method("validate"):
			findings.append(_file(path, "Validator must implement validate(context)."))
			continue
		var result: Variant = instance.validate({
			"project_dir": project_dir,
			"editor": false,
			"include_warnings": include_warnings,
		})
		if not (result is Array):
			findings.append(_file(path, "Validator must return an Array of findings."))
		else:
			for item in result:
				if not (item is Dictionary):
					findings.append(_file(path, "Validator returned a non-Dictionary finding."))
					continue
				var finding: Dictionary = (item as Dictionary).duplicate()
				finding["validator"] = path
				if not ["error", "warning", "info"].has(str(finding.get("severity", "error"))):
					finding["severity"] = "error"
				finding["path"] = str(finding.get("path", ""))
				finding["message"] = str(finding.get("message", "Validator finding."))
				findings.append(finding)
		if instance is Object and not (instance is RefCounted):
			instance.free()


## Every file under `dir`, skipping engine/VCS cache directories.
static func _files(dir: String) -> Array:
	var out: Array = []
	var handle := DirAccess.open(dir)
	if handle == null:
		return out
	handle.list_dir_begin()
	var name := handle.get_next()
	while name != "":
		if name.begins_with(".") or SKIP_DIRS.has(name):
			name = handle.get_next()
			continue
		var full := dir.path_join(name)
		if handle.current_is_dir():
			out.append_array(_files(full))
		else:
			out.append(full)
		name = handle.get_next()
	handle.list_dir_end()
	return out
