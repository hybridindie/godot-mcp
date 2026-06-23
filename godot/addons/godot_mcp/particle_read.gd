@tool
class_name MCPParticleRead
extends RefCounted
## Pure, read-only serialization of a ParticleProcessMaterial (issue #219 P4 — rollback
## enabler). Takes the material resource (never EditorInterface), so it is verifiable
## headlessly (see godot/tests/particle_read_smoke.gd). Inverts set_particle_material /
## set_particle_color_gradient: ``properties`` are the JSON-coerced material fields and
## ``color_ramp`` is the gradient's stops (not a sub-resource ref) so it round-trips.

const Inspect := preload("res://addons/godot_mcp/scene_inspect.gd")


## { has_material, properties:{...}, color_ramp:{colors:[{r,g,b,a}], offsets:[float]}|null }.
static func serialize(material: Variant) -> Dictionary:
	if not (material is ParticleProcessMaterial):
		return {"has_material": false, "properties": {}, "color_ramp": null}
	# All editable/stored material props, JSON-coerced. color_ramp is a sub-resource
	# (GradientTexture) that resource_properties would flatten to a class name, so drop
	# it here and serialize the gradient detail separately.
	var props: Dictionary = Inspect.resource_properties(material)
	props.erase("color_ramp")
	return {
		"has_material": true,
		"properties": props,
		"color_ramp": _serialize_ramp(material.color_ramp),
	}


## A GradientTexture1D's gradient as parallel { colors, offsets }, or null.
static func _serialize_ramp(tex: Variant) -> Variant:
	if tex == null:
		return null
	var gradient: Variant = tex.get("gradient")
	if not (gradient is Gradient):
		return null
	var colors: Array = []
	var offsets: Array = []
	for i in gradient.get_point_count():
		var c: Color = gradient.get_color(i)
		colors.append({"r": c.r, "g": c.g, "b": c.b, "a": c.a})
		offsets.append(gradient.get_offset(i))
	return {"colors": colors, "offsets": offsets}
