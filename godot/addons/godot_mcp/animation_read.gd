@tool
class_name MCPAnimationRead
extends RefCounted
## Pure, read-only serialization of Animation resources (issue #218 — rollback
## enabler G4). Takes Animation/AnimationPlayer resources (never EditorInterface),
## so it is verifiable headlessly (see godot/tests/animation_smoke.gd). Keyframe
## values are JSON-safe via MCPTypeCoerce. Inverts the animation writers
## (create_animation / add_animation_track / insert_keyframe).

const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")

# Animation.TrackType enum → the names the writer accepts (mirror of the handler's
# _TRACK_TYPES), so a read round-trips back into add_animation_track.
const _TYPE_NAMES := {
	Animation.TYPE_VALUE: "value",
	Animation.TYPE_POSITION_3D: "position_3d",
	Animation.TYPE_ROTATION_3D: "rotation_3d",
	Animation.TYPE_SCALE_3D: "scale_3d",
	Animation.TYPE_METHOD: "method",
	Animation.TYPE_BEZIER: "bezier",
	Animation.TYPE_AUDIO: "audio",
	Animation.TYPE_ANIMATION: "animation",
}


## All animation names on a player (across its libraries), as plain strings.
static func names(player: AnimationPlayer) -> Array:
	var out: Array = []
	for n in player.get_animation_list():
		out.append(String(n))
	return out


## { name, length, tracks:[{type, path, keys:[{time, value}]}] }, JSON-coerced.
static func serialize(anim_name: String, animation: Animation) -> Dictionary:
	var tracks: Array = []
	for i in animation.get_track_count():
		var keys: Array = []
		for k in animation.track_get_key_count(i):
			keys.append({
				"time": animation.track_get_key_time(i, k),
				"value": Coerce.to_json(animation.track_get_key_value(i, k)),
			})
		tracks.append({
			"type": _TYPE_NAMES.get(animation.track_get_type(i), "unknown"),
			"path": String(animation.track_get_path(i)),
			"keys": keys,
		})
	return {"name": anim_name, "length": animation.length, "tracks": tracks}
