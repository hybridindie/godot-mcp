@tool
class_name MCPPhysicsRead
extends RefCounted
## Godot 4.8 runtime physics read-back: capability gate + query vocabulary (#599).
##
## The APIs behind this surface are 4.8-only:
## ``RigidBody2D/3D.get_velocity_at_position()`` /
## ``get_velocity_at_local_position()`` and the non-allocating
## ``PhysicsDirectSpaceState2D/3D.*_into()`` queries. They are NEVER referenced
## statically here or at the call sites — a static reference makes the addon
## unparseable on the 4.4–4.7 floor (the editor parses every script). Detection
## is ClassDB-based, never a version-string parse.
##
## Shared by the editor handler (``handlers/runtime_inspect.gd`` — the structured
## UNSUPPORTED envelope) and the in-game probe (``mcp_runtime_probe.gd`` — the
## defence-in-depth reply), so both sides use one vocabulary and one hint text.

## Query method → the engine's ``*_into`` method name.
const QUERY_METHODS := {
	"intersect_ray": "intersect_ray_into",
	"intersect_point": "intersect_point_into",
	"intersect_shape": "intersect_shape_into",
	"cast_motion": "cast_motion_into",
	"collide_shape": "collide_shape_into",
	"get_rest_info": "get_rest_info_into",
}

## Query method → the preallocated result class (without the 2D/3D suffix).
const QUERY_RESULTS := {
	"intersect_ray": "PhysicsIntersectRayResult",
	"intersect_point": "PhysicsIntersectPointResult",
	"intersect_shape": "PhysicsIntersectShapeResult",
	"cast_motion": "PhysicsCastMotionResult",
	"collide_shape": "PhysicsCollideShapeResult",
	"get_rest_info": "PhysicsGetRestInfoResult",
}

## Query method → the ``Physics*QueryParameters`` family (without the 2D/3D suffix).
const QUERY_PARAMETER_FAMILIES := {
	"intersect_ray": "Ray",
	"intersect_point": "Point",
	"intersect_shape": "Shape",
	"cast_motion": "Shape",
	"collide_shape": "Shape",
	"get_rest_info": "Shape",
}

const VELOCITY_METHODS := ["get_velocity_at_position", "get_velocity_at_local_position"]


## The velocity-at-point methods exist on both RigidBody dimensions (4.8+).
static func velocity_supported() -> bool:
	for cls in ["RigidBody2D", "RigidBody3D"]:
		for engine_method in VELOCITY_METHODS:
			if not ClassDB.class_has_method(cls, engine_method):
				return false
	return true


## Actionable hint for a 4.4–4.7 editor (detection is ClassDB; the version text is
## only for the message). Empty when supported.
static func velocity_hint() -> String:
	if velocity_supported():
		return ""
	return (
		"RigidBody2D/3D.get_velocity_at_position() and get_velocity_at_local_position() "
		+ "require Godot 4.8+ (this editor is %s). Use runtime_read_property on "
		+ "'linear_velocity' for the centre-of-mass velocity."
	) % _godot_version()


## The ``*_into`` method + typed result class exist for this dimension (4.8+).
static func space_query_supported(method: String, dimension: String) -> bool:
	if not QUERY_METHODS.has(method):
		return false
	var suffix := _suffix(dimension)
	var result_class := str(QUERY_RESULTS[method]) + suffix
	var state_class := "PhysicsDirectSpaceState" + suffix
	return (
		ClassDB.class_exists(result_class)
		and ClassDB.class_has_method(state_class, str(QUERY_METHODS[method]))
	)


## Actionable hint for a 4.4–4.7 editor. Empty when supported.
static func space_query_hint(method: String, dimension: String) -> String:
	if space_query_supported(method, dimension):
		return ""
	var suffix := _suffix(dimension)
	var engine_method := str(QUERY_METHODS.get(method, ""))
	var result_class := str(QUERY_RESULTS.get(method, "")) + suffix
	if engine_method.is_empty():
		return "Unknown physics space query method '%s'." % method
	return (
		"PhysicsDirectSpaceState%s.%s() and its preallocated %s result require "
		+ "Godot 4.8+ (this editor is %s)."
	) % [suffix, engine_method, result_class, _godot_version()]


static func _suffix(dimension: String) -> String:
	return "3D" if dimension == "3d" else "2D"


static func _godot_version() -> String:
	return str(Engine.get_version_info().get("string", "unknown"))
