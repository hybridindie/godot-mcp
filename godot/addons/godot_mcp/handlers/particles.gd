@tool
class_name MCPParticlesHandlers
extends RefCounted
const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")
const ParticleRead := preload("res://addons/godot_mcp/particle_read.gd")
## Domain handler: particles.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

const _PARTICLE_PRESETS := {
	"fire": {
		"node": {"amount": 32, "lifetime": 1.0, "explosiveness": 0.1},
		"material": {
			"direction": {"x": 0, "y": -1, "z": 0}, "spread": 20.0,
			"gravity": {"x": 0, "y": -30, "z": 0},
			"initial_velocity_min": 30.0, "initial_velocity_max": 60.0,
			"scale_min": 1.5, "scale_max": 3.0, "color": "#ffcc33",
		},
		"gradient": ["#ffee88ff", "#ff6600cc", "#cc220000"],
	},
	"smoke": {
		"node": {"amount": 24, "lifetime": 2.5, "explosiveness": 0.0},
		"material": {
			"direction": {"x": 0, "y": -1, "z": 0}, "spread": 12.0,
			"gravity": {"x": 0, "y": -8, "z": 0},
			"initial_velocity_min": 8.0, "initial_velocity_max": 18.0,
			"scale_min": 2.0, "scale_max": 5.0, "color": "#888888",
		},
		"gradient": ["#aaaaaaaa", "#66666666", "#33333300"],
	},
	"explosion": {
		"node": {"amount": 48, "lifetime": 0.8, "one_shot": true, "explosiveness": 1.0},
		"material": {
			"spread": 180.0, "gravity": {"x": 0, "y": 0, "z": 0},
			"initial_velocity_min": 60.0, "initial_velocity_max": 140.0,
			"scale_min": 1.0, "scale_max": 2.5, "color": "#ffaa33",
			"damping_min": 20.0, "damping_max": 40.0,
		},
		"gradient": ["#ffffccff", "#ff8800cc", "#88110000"],
	},
	"sparks": {
		"node": {"amount": 24, "lifetime": 0.6, "explosiveness": 0.4},
		"material": {
			"spread": 45.0, "gravity": {"x": 0, "y": 60, "z": 0},
			"initial_velocity_min": 40.0, "initial_velocity_max": 90.0,
			"scale_min": 0.4, "scale_max": 1.0, "color": "#ffee99",
		},
		"gradient": ["#ffffddff", "#ffcc33ff", "#ff660000"],
	},
}

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_apply_particle_preset"] = _cmd_apply_particle_preset
	handlers["cmd_create_particles"] = _cmd_create_particles
	handlers["cmd_set_particle_color_gradient"] = _cmd_set_particle_color_gradient
	handlers["cmd_set_particle_material"] = _cmd_set_particle_material
	handlers["cmd_get_particle_material"] = _cmd_get_particle_material


# -- handlers ----------------------------------------------------------------

func _cmd_create_particles(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var particles_type := str(params.get("particles_type", "GPUParticles2D"))
	if particles_type != "GPUParticles2D" and particles_type != "GPUParticles3D":
		return _router._fail("VALIDATION_ERROR", "particles_type must be GPUParticles2D or GPUParticles3D.")
	var particles := ClassDB.instantiate(particles_type) as Node
	if particles == null:
		return _router._fail("VALIDATION_ERROR", "Could not instantiate '%s'." % particles_type)
	particles.name = str(params.get("name", particles_type))
	particles.set("amount", maxi(1, int(params.get("amount", 8))))
	particles.set("lifetime", maxf(0.01, float(params.get("lifetime", 1.0))))
	particles.set("process_material", ParticleProcessMaterial.new())
	_router._apply_props(particles, params.get("properties", {}))
	var path := _router._commit_add_child(parent, particles, "Add %s" % particles.name)
	return _router._ok({"node_path": path, "particles_type": particles_type, "created": true})



func _cmd_set_particle_material(params: Dictionary) -> Dictionary:
	var found := _resolve_particles(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var properties: Dictionary = params.get("properties", {})
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Configure particle material")
	var material := _stage_process_material(node, ur)
	for key in properties:
		var pt := _router._property_type(material, str(key))
		if pt != -1:
			ur.add_do_property(material, str(key), Coerce.from_json(properties[key], pt))
			ur.add_undo_property(material, str(key), material.get(str(key)))
	ur.commit_action()
	return _router._ok({"node_path": str(params.get("node_path")), "properties": _applied_props(material, properties)})



func _cmd_set_particle_color_gradient(params: Dictionary) -> Dictionary:
	var found := _resolve_particles(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var raw_colors: Variant = params.get("colors")
	if not (raw_colors is Array) or (raw_colors as Array).is_empty():
		return _router._fail("VALIDATION_ERROR", "'colors' must be a non-empty array of color stops.")
	var texture := _build_gradient_texture(raw_colors, params.get("offsets"))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set particle color gradient")
	var material := _stage_process_material(node, ur)
	ur.add_do_property(material, "color_ramp", texture)
	ur.add_do_reference(texture)
	ur.add_undo_property(material, "color_ramp", material.color_ramp)
	ur.commit_action()
	return _router._ok({"node_path": str(params.get("node_path")), "stops": (raw_colors as Array).size()})



func _cmd_apply_particle_preset(params: Dictionary) -> Dictionary:
	var found := _resolve_particles(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var preset_name := str(params.get("preset", ""))
	if not _PARTICLE_PRESETS.has(preset_name):
		return _router._fail("VALIDATION_ERROR", "Unknown preset '%s'." % preset_name)
	var preset: Dictionary = _PARTICLE_PRESETS[preset_name]
	var node_props: Dictionary = preset.get("node", {})
	var mat_props: Dictionary = preset.get("material", {})
	var grad_colors: Array = preset.get("gradient", [])
	var material := ParticleProcessMaterial.new()
	_router._apply_props(material, mat_props)
	if not grad_colors.is_empty():
		material.color_ramp = _build_gradient_texture(grad_colors, null)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Apply particle preset %s" % preset_name)
	ur.add_do_property(node, "process_material", material)
	ur.add_do_reference(material)
	ur.add_undo_property(node, "process_material", node.process_material)
	for key in node_props:
		var pt := _router._property_type(node, str(key))
		if pt != -1:
			ur.add_do_property(node, str(key), Coerce.from_json(node_props[key], pt))
			ur.add_undo_property(node, str(key), node.get(str(key)))
	ur.commit_action()
	return _router._ok({"node_path": str(params.get("node_path")), "preset": preset_name})


## Read a particle node's ProcessMaterial — props + color ramp (issue #219 P4). The
## inverse of set_particle_material / set_particle_color_gradient; delegates the pure
## serialization to MCPParticleRead.
func _cmd_get_particle_material(params: Dictionary) -> Dictionary:
	var found := _resolve_particles(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var data: Dictionary = ParticleRead.serialize(node.process_material)
	data["node_path"] = str(params.get("node_path"))
	return _router._ok(data)


func _resolve_particles(raw_path: Variant) -> Dictionary:
	var found := _router._resolve(raw_path)
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if not (node is GPUParticles2D or node is GPUParticles3D):
		return _router._fail("VALIDATION_ERROR", "Node is not a GPUParticles2D/GPUParticles3D.")
	return {"ok": true, "node": node}


func _stage_process_material(node: Node, ur: EditorUndoRedoManager) -> ParticleProcessMaterial:
	var existing: Variant = node.process_material
	if existing is ParticleProcessMaterial:
		return existing
	var material := ParticleProcessMaterial.new()
	ur.add_do_property(node, "process_material", material)
	ur.add_do_reference(material)
	ur.add_undo_property(node, "process_material", existing)
	return material


func _build_gradient_texture(raw_colors: Array, raw_offsets: Variant) -> GradientTexture1D:
	var colors := PackedColorArray()
	for c in raw_colors:
		colors.append(Coerce.from_json(c, TYPE_COLOR))
	var count := colors.size()
	var offsets := PackedFloat32Array()
	if raw_offsets is Array and (raw_offsets as Array).size() == count:
		for o in raw_offsets:
			offsets.append(clampf(float(o), 0.0, 1.0))
	else:
		for i in count:
			offsets.append(0.0 if count <= 1 else float(i) / float(count - 1))
	var gradient := Gradient.new()
	gradient.offsets = offsets
	gradient.colors = colors
	var texture := GradientTexture1D.new()
	texture.gradient = gradient
	return texture


func _applied_props(obj: Object, props: Dictionary) -> Dictionary:
	var applied: Dictionary = {}
	for key in props:
		if _router._property_type(obj, str(key)) != -1:
			applied[str(key)] = Coerce.to_json(obj.get(str(key)))
	return applied


