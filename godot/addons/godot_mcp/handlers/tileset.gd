@tool
class_name MCPTileSetHandlers
extends RefCounted
## Domain handler: tileset.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_add_tileset_atlas_source"] = _cmd_add_tileset_atlas_source
	handlers["cmd_create_tile"] = _cmd_create_tile
	handlers["cmd_create_tileset"] = _cmd_create_tileset


# -- handlers ----------------------------------------------------------------

func _cmd_create_tileset(params: Dictionary) -> Dictionary:
	var node_path := str(params.get("node_path", ""))
	var save_path := str(params.get("save_path", ""))
	if node_path.is_empty() and save_path.is_empty():
		return _router._fail("VALIDATION_ERROR", "Provide 'node_path' to assign the TileSet and/or 'save_path' to save it as a .tres.")
	var size_res := _router._parse_vec2i(params.get("tile_size", [16, 16]), "tile_size")
	if not size_res["ok"]:
		return size_res
	var tile_size: Vector2i = size_res["value"]
	if tile_size.x <= 0 or tile_size.y <= 0:
		return _router._fail("VALIDATION_ERROR", "'tile_size' components must be positive.")
	var tileset := TileSet.new()
	tileset.tile_size = tile_size
	if not save_path.is_empty():
		if not save_path.begins_with("res://"):
			return _router._fail("VALIDATION_ERROR", "save_path must be a res:// path.")
		var saved := _save_tileset_file(tileset, save_path)
		if not saved["ok"]:
			return saved
		tileset.take_over_path(save_path)
	if not node_path.is_empty():
		var found := _router._resolve(node_path)
		if not found["ok"]:
			return found
		var node: Node = found["node"]
		if not (node is TileMapLayer or node is TileMap):
			return _router._fail("VALIDATION_ERROR", "Node is not a TileMap/TileMapLayer.")
		var prev: TileSet = node.tile_set
		var ur := EditorInterface.get_editor_undo_redo()
		ur.create_action("Create TileSet on %s" % node.name)
		ur.add_do_property(node, "tile_set", tileset)
		ur.add_do_reference(tileset)
		ur.add_undo_property(node, "tile_set", prev)
		if prev != null:  # keep the prior TileSet alive for undo
			ur.add_undo_reference(prev)
		ur.commit_action()
	return _router._ok({
		"node_path": node_path,
		"tileset_path": save_path,
		"tile_size": [tile_size.x, tile_size.y],
		"created": true,
	})



func _cmd_add_tileset_atlas_source(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tileset(params)
	if not resolved["ok"]:
		return resolved
	var tileset: TileSet = resolved["tileset"]
	var texture_path := str(params.get("texture_path", ""))
	if texture_path.is_empty():
		return _router._fail("VALIDATION_ERROR", "'texture_path' must be the path to an imported Texture2D (e.g. res://art/tiles.png).")
	if not ResourceLoader.exists(texture_path):
		return _router._fail("RESOURCE_NOT_FOUND", "No resource at '%s'. Import the texture into the project first." % texture_path)
	var tex_res: Resource = ResourceLoader.load(texture_path)
	if not (tex_res is Texture2D):
		return _router._fail("VALIDATION_ERROR", "'%s' is not a Texture2D." % texture_path)
	var region_res := _router._parse_vec2i(params.get("region_size", [16, 16]), "region_size")
	if not region_res["ok"]:
		return region_res
	var region: Vector2i = region_res["value"]
	if region.x <= 0 or region.y <= 0:
		return _router._fail("VALIDATION_ERROR", "'region_size' components must be positive.")
	var requested: Variant = params.get("source_id")
	var source_id := int(requested) if requested != null else tileset.get_next_source_id()
	if source_id < 0:
		return _router._fail("VALIDATION_ERROR", "'source_id' must be non-negative.")
	if tileset.has_source(source_id):
		return _router._fail("VALIDATION_ERROR", "Source id %d already exists in the TileSet." % source_id)
	var source := TileSetAtlasSource.new()
	source.texture = tex_res as Texture2D
	source.texture_region_size = region
	if resolved["backing"] == "node":
		var ur := EditorInterface.get_editor_undo_redo()
		ur.create_action("Add atlas source to TileSet")
		ur.add_do_method(tileset, "add_source", source, source_id)
		ur.add_do_reference(source)
		ur.add_undo_method(tileset, "remove_source", source_id)
		ur.commit_action()
	else:
		tileset.add_source(source, source_id)
		var saved := _save_tileset_file(tileset, resolved["path"])
		if not saved["ok"]:
			return saved
	return _router._ok({
		"node_path": str(params.get("node_path", "")),
		"tileset_path": str(params.get("tileset_path", "")),
		"source_id": source_id,
		"texture_path": texture_path,
		"region_size": [region.x, region.y],
	})



func _cmd_create_tile(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tileset(params)
	if not resolved["ok"]:
		return resolved
	var tileset: TileSet = resolved["tileset"]
	var source_id := int(params.get("source_id", -1))
	if not tileset.has_source(source_id):
		return _router._fail("VALIDATION_ERROR", "No source with id %d; add one with add_tileset_atlas_source." % source_id, "source_id")
	var source_obj: Object = tileset.get_source(source_id)
	if not (source_obj is TileSetAtlasSource):
		return _router._fail("VALIDATION_ERROR", "Source %d is not a TileSetAtlasSource." % source_id)
	var source: TileSetAtlasSource = source_obj
	var coords_res := _router._parse_vec2i(params.get("atlas_coords"), "atlas_coords")
	if not coords_res["ok"]:
		return coords_res
	var coords: Vector2i = coords_res["value"]
	var size_res := _router._parse_vec2i(params.get("size", [1, 1]), "size")
	if not size_res["ok"]:
		return size_res
	var size: Vector2i = size_res["value"]
	if size.x <= 0 or size.y <= 0:
		return _router._fail("VALIDATION_ERROR", "'size' components must be positive.")
	# has_room_for_tile guards both out-of-atlas coords and overlap with existing tiles.
	if not source.has_room_for_tile(coords, size, 1, Vector2i.ZERO, 1):
		return _router._fail("VALIDATION_ERROR", "No room for a tile at %v size %v (out of the atlas grid or overlapping an existing tile)." % [coords, size])
	if resolved["backing"] == "node":
		var ur := EditorInterface.get_editor_undo_redo()
		ur.create_action("Create tile %v" % coords)
		ur.add_do_method(source, "create_tile", coords, size)
		ur.add_undo_method(source, "remove_tile", coords)
		ur.commit_action()
	else:
		source.create_tile(coords, size)
		var saved := _save_tileset_file(tileset, resolved["path"])
		if not saved["ok"]:
			return saved
	return _router._ok({
		"node_path": str(params.get("node_path", "")),
		"tileset_path": str(params.get("tileset_path", "")),
		"source_id": source_id,
		"atlas_coords": [coords.x, coords.y],
		"size": [size.x, size.y],
	})


func _resolve_tileset(params: Dictionary) -> Dictionary:
	var node_path := str(params.get("node_path", ""))
	var tileset_path := str(params.get("tileset_path", ""))
	if not node_path.is_empty() and not tileset_path.is_empty():
		return _router._fail("VALIDATION_ERROR", "Pass only one of 'node_path' or 'tileset_path', not both.")
	if not node_path.is_empty():
		var found := _router._resolve(node_path)
		if not found["ok"]:
			return found
		var node: Node = found["node"]
		if not (node is TileMapLayer or node is TileMap):
			return _router._fail("VALIDATION_ERROR", "Node is not a TileMap/TileMapLayer.")
		var ts: TileSet = node.tile_set
		if ts == null:
			return _router._fail("VALIDATION_ERROR", "Node has no tile_set; create one first with create_tileset.", "tile_set")
		return {"ok": true, "tileset": ts, "backing": "node", "node": node}
	if not tileset_path.is_empty():
		if not ResourceLoader.exists(tileset_path):
			return _router._fail("RESOURCE_NOT_FOUND", "No resource at '%s'." % tileset_path)
		var res: Resource = ResourceLoader.load(tileset_path)
		if not (res is TileSet):
			return _router._fail("VALIDATION_ERROR", "'%s' is not a TileSet." % tileset_path)
		return {"ok": true, "tileset": res, "backing": "file", "path": tileset_path}
	return _router._fail("VALIDATION_ERROR", "Provide a 'node_path' (TileMap/TileMapLayer) or a 'tileset_path' (.tres).")


func _save_tileset_file(tileset: TileSet, path: String) -> Dictionary:
	var err := ResourceSaver.save(tileset, path)
	if err != OK:
		return _router._fail("INTERNAL_ERROR", "Failed to save TileSet to '%s' (error %d)." % [path, err])
	EditorInterface.get_resource_filesystem().update_file(path)
	return {"ok": true}


