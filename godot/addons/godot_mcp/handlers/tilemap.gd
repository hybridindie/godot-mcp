@tool
class_name MCPTileMapHandlers
extends RefCounted
## Domain handler: tilemap.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

const _TILEMAP_FILL_LIMIT := 16384  # max cells per fill_rect (128x128) to bound undo size

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_tilemap_clear"] = _cmd_tilemap_clear
	handlers["cmd_tilemap_fill_rect"] = _cmd_tilemap_fill_rect
	handlers["cmd_tilemap_get_cell"] = _cmd_tilemap_get_cell
	handlers["cmd_tilemap_get_used_cells"] = _cmd_tilemap_get_used_cells
	handlers["cmd_tilemap_layers"] = _cmd_tilemap_layers
	handlers["cmd_tilemap_set_cell"] = _cmd_tilemap_set_cell


# -- handlers ----------------------------------------------------------------

func _cmd_tilemap_set_cell(params: Dictionary) -> Dictionary:
	var found := _resolve_tilemap(params.get("node_path", ""), int(params.get("layer", 0)))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var layer := int(params.get("layer", 0))
	var coords_res := _router._parse_vec2i(params.get("coords"), "coords")
	if not coords_res["ok"]:
		return coords_res
	var atlas_res := _router._parse_vec2i(params.get("atlas_coords", [0, 0]), "atlas_coords")
	if not atlas_res["ok"]:
		return atlas_res
	var coords: Vector2i = coords_res["value"]
	var source_id := int(params.get("source_id", -1))
	var atlas: Vector2i = atlas_res["value"]
	var alt := int(params.get("alternative_tile", 0))
	var prev := _read_tile_cell(node, layer, coords)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set tile %v" % coords)
	ur.add_do_method(self, "_apply_tile_cell", node, layer, coords, source_id, atlas, alt)
	ur.add_undo_method(
		self, "_apply_tile_cell", node, layer, coords,
		prev["source_id"], prev["atlas_coords"], prev["alternative_tile"]
	)
	ur.commit_action()
	return _router._ok({
		"node_path": str(params.get("node_path")),
		"coords": [coords.x, coords.y],
		"source_id": source_id,
		"layer": layer,
	})



func _cmd_tilemap_fill_rect(params: Dictionary) -> Dictionary:
	var found := _resolve_tilemap(params.get("node_path", ""), int(params.get("layer", 0)))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var layer := int(params.get("layer", 0))
	var raw_rect: Variant = params.get("rect")
	if not (raw_rect is Array) or (raw_rect as Array).size() != 4:
		return _router._fail("VALIDATION_ERROR", "'rect' must be [x, y, w, h].")
	var width := int(raw_rect[2])
	var height := int(raw_rect[3])
	if width <= 0 or height <= 0:
		return _router._fail("VALIDATION_ERROR", "rect width and height must be positive.")
	if width * height > _TILEMAP_FILL_LIMIT:
		return _router._fail("VALIDATION_ERROR", "Fill region %dx%d exceeds the %d-cell limit; fill smaller rects." % [width, height, _TILEMAP_FILL_LIMIT])
	var atlas_res := _router._parse_vec2i(params.get("atlas_coords", [0, 0]), "atlas_coords")
	if not atlas_res["ok"]:
		return atlas_res
	var origin := Vector2i(int(raw_rect[0]), int(raw_rect[1]))
	var source_id := int(params.get("source_id", -1))
	var atlas: Vector2i = atlas_res["value"]
	var alt := int(params.get("alternative_tile", 0))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Fill tiles %dx%d" % [width, height])
	var count := 0
	for dy in height:
		for dx in width:
			var coords := origin + Vector2i(dx, dy)
			var prev := _read_tile_cell(node, layer, coords)
			ur.add_do_method(self, "_apply_tile_cell", node, layer, coords, source_id, atlas, alt)
			ur.add_undo_method(
				self, "_apply_tile_cell", node, layer, coords,
				prev["source_id"], prev["atlas_coords"], prev["alternative_tile"]
			)
			count += 1
	ur.commit_action()
	return _router._ok({
		"node_path": str(params.get("node_path")),
		"rect": [origin.x, origin.y, width, height],
		"cells": count,
		"layer": layer,
	})



func _cmd_tilemap_get_cell(params: Dictionary) -> Dictionary:
	var found := _resolve_tilemap(params.get("node_path", ""), int(params.get("layer", 0)))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var layer := int(params.get("layer", 0))
	var coords_res := _router._parse_vec2i(params.get("coords"), "coords")
	if not coords_res["ok"]:
		return coords_res
	var coords: Vector2i = coords_res["value"]
	var cell := _read_tile_cell(node, layer, coords)
	var atlas: Vector2i = cell["atlas_coords"]
	return _router._ok({
		"node_path": str(params.get("node_path")),
		"coords": [coords.x, coords.y],
		"source_id": cell["source_id"],
		"atlas_coords": [atlas.x, atlas.y],
		"alternative_tile": cell["alternative_tile"],
		"empty": cell["source_id"] == -1,
	})


## Bulk snapshot of every painted cell on a layer (issue #219 P3) — the inverse of
## tilemap_fill_rect / tilemap_clear. Reuses the _used_cells + _read_tile_cell helpers.
func _cmd_tilemap_get_used_cells(params: Dictionary) -> Dictionary:
	var found := _resolve_tilemap(params.get("node_path", ""), int(params.get("layer", 0)))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var layer := int(params.get("layer", 0))
	var cells: Array = []
	for coords in _used_cells(node, layer):
		var cell := _read_tile_cell(node, layer, coords)
		var atlas: Vector2i = cell["atlas_coords"]
		cells.append({
			"coords": [coords.x, coords.y],
			"source_id": cell["source_id"],
			"atlas_coords": [atlas.x, atlas.y],
			"alternative_tile": cell["alternative_tile"],
		})
	return _router._ok({
		"node_path": str(params.get("node_path")),
		"layer": layer,
		"count": cells.size(),
		"cells": cells,
	})



func _cmd_tilemap_clear(params: Dictionary) -> Dictionary:
	var requested_layer: Variant = params.get("layer")
	var layer := int(requested_layer) if requested_layer != null else 0
	var found := _resolve_tilemap(params.get("node_path", ""), layer)
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	# Snapshot the cells so undo can restore them, then clear. Bound the snapshot so a
	# huge layer can't build an enormous UndoRedo action and stall the editor.
	var used: Array = _used_cells(node, layer)
	if used.size() > _TILEMAP_FILL_LIMIT:
		return _router._fail("VALIDATION_ERROR", "Layer has %d cells, over the %d-cell undoable-clear limit; clear smaller regions with fill_rect (source_id=-1)." % [used.size(), _TILEMAP_FILL_LIMIT])
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Clear tiles")
	ur.add_do_method(self, "_clear_tile_layer", node, layer)
	for coords in used:
		var prev := _read_tile_cell(node, layer, coords)
		ur.add_undo_method(
			self, "_apply_tile_cell", node, layer, coords,
			prev["source_id"], prev["atlas_coords"], prev["alternative_tile"]
		)
	ur.commit_action()
	# TileMapLayer has no layer concept; report null. TileMap reports the cleared layer.
	var result_layer: Variant = null if node is TileMapLayer else layer
	return _router._ok({
		"node_path": str(params.get("node_path")),
		"layer": result_layer,
		"cleared": used.size(),
	})



func _cmd_tilemap_layers(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var layers: Array = []
	if node is TileMapLayer:
		layers.append({"index": 0, "name": String(node.name), "enabled": node.enabled})
	elif node is TileMap:
		for i in node.get_layers_count():
			layers.append({
				"index": i,
				"name": node.get_layer_name(i),
				"enabled": node.is_layer_enabled(i),
			})
	else:
		return _router._fail("VALIDATION_ERROR", "Node is not a TileMap/TileMapLayer.")
	return _router._ok({
		"node_path": str(params.get("node_path")),
		"node_type": node.get_class(),
		"layers": layers,
	})


func _resolve_tilemap(raw_path: Variant, layer: int) -> Dictionary:
	var found := _router._resolve(raw_path)
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if node is TileMapLayer:
		return {"ok": true, "node": node}
	if node is TileMap:
		if layer < 0 or layer >= node.get_layers_count():
			return _router._fail("VALIDATION_ERROR", "Layer %d is out of range (0..%d)." % [layer, node.get_layers_count() - 1])
		return {"ok": true, "node": node}
	return _router._fail("VALIDATION_ERROR", "Node is not a TileMap/TileMapLayer.")


func _apply_tile_cell(
	node: Node, layer: int, coords: Vector2i, source_id: int, atlas_coords: Vector2i, alternative_tile: int
) -> void:
	if node is TileMapLayer:
		node.set_cell(coords, source_id, atlas_coords, alternative_tile)
	else:
		node.set_cell(layer, coords, source_id, atlas_coords, alternative_tile)

func _clear_tile_layer(node: Node, layer: int) -> void:
	if node is TileMapLayer:
		node.clear()
	else:
		node.clear_layer(layer)


func _read_tile_cell(node: Node, layer: int, coords: Vector2i) -> Dictionary:
	if node is TileMapLayer:
		return {
			"source_id": node.get_cell_source_id(coords),
			"atlas_coords": node.get_cell_atlas_coords(coords),
			"alternative_tile": node.get_cell_alternative_tile(coords),
		}
	return {
		"source_id": node.get_cell_source_id(layer, coords),
		"atlas_coords": node.get_cell_atlas_coords(layer, coords),
		"alternative_tile": node.get_cell_alternative_tile(layer, coords),
	}


func _used_cells(node: Node, layer: int) -> Array:
	if node is TileMapLayer:
		return node.get_used_cells()
	return node.get_used_cells(layer)


