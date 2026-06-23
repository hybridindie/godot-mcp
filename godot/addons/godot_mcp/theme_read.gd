@tool
class_name MCPThemeRead
extends RefCounted
## Pure, read-only serialization of a Control's per-node theme overrides (issue #219
## G7 — rollback enabler). Takes a Control (never EditorInterface), so verifiable
## headlessly (see godot/tests/theme_read_smoke.gd). Inverts set_theme_color /
## set_theme_font_size / set_theme_stylebox.

const Inspect := preload("res://addons/godot_mcp/scene_inspect.gd")
const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")


const _COLOR_PREFIX := "theme_override_colors/"
const _FONT_SIZE_PREFIX := "theme_override_font_sizes/"
const _STYLEBOX_PREFIX := "theme_override_styles/"


## { colors:{name:{r,g,b,a}}, font_sizes:{name:int}, styleboxes:[{name, type, properties}] }.
## Styleboxes carry their class + serialized props so they round-trip into set_theme_stylebox.
##
## Godot 4.x has no get_theme_*_override_list; overrides surface in the property list as
## theme_override_colors/<name>, theme_override_font_sizes/<name>, theme_override_styles/
## <name>. Those entries exist for *every* known theme item, so each is gated on
## has_theme_*_override to keep only the ones actually set on this node.
static func overrides(node: Control) -> Dictionary:
	var colors: Dictionary = {}
	var font_sizes: Dictionary = {}
	var styleboxes: Array = []
	for prop in node.get_property_list():
		var pname: String = prop.get("name", "")
		if pname.begins_with(_COLOR_PREFIX):
			var cname := pname.substr(_COLOR_PREFIX.length())
			if node.has_theme_color_override(cname):
				colors[cname] = Coerce.to_json(node.get_theme_color(cname))
		elif pname.begins_with(_FONT_SIZE_PREFIX):
			var fname := pname.substr(_FONT_SIZE_PREFIX.length())
			if node.has_theme_font_size_override(fname):
				font_sizes[fname] = node.get_theme_font_size(fname)
		elif pname.begins_with(_STYLEBOX_PREFIX):
			var sname := pname.substr(_STYLEBOX_PREFIX.length())
			if node.has_theme_stylebox_override(sname):
				var sb: StyleBox = node.get_theme_stylebox(sname)
				styleboxes.append({
					"name": sname,
					"type": sb.get_class(),
					"properties": Inspect.resource_properties(sb),
				})
	return {"colors": colors, "font_sizes": font_sizes, "styleboxes": styleboxes}
