# TileSet & GridMap Authoring

TileMap painting needs a **TileSet resource** first; GridMap cells need a
**MeshLibrary resource** first. Both are resources — the node alone places
nothing. This is the `tilemap` and `scene_3d` toolsets.

## The TileSet chain (2D)

A placeable tile requires **four** things in order. Skipping a link fails the
next call:

```
create_tileset → add_tileset_atlas_source → create_tile → tilemap_set_cell
     (the grid)        (slice a texture)      (mark a cell)    (paint it)
```

| Step | Tool | What it makes |
|------|------|---------------|
| 1 | `godot_tilemap_create_tileset(node_path, tile_size=[w,h])` | the TileSet (grid cell size) |
| 2 | `godot_tilemap_add_tileset_atlas_source(texture_path, region_size=[w,h])` | an atlas source; returns `source_id` |
| 3 | `godot_tilemap_create_tile(source_id, atlas_coords=[x,y])` | makes that atlas cell placeable |
| 4 | `godot_tilemap_set_cell(node_path, position=[x,y], source_id, atlas_coords)` | paints one cell |

Target the TileSet by **`node_path` (an in-scene TileMap/TileMapLayer) or
`tileset_path` (a saved `.tres`) — pass exactly one.** `create_tileset` accepts
one or both (assign *and* save).

### Pitfalls

- **No tiles = blank map.** If `create_tile` was never called for a cell's
  `source_id`/`atlas_coords`, `set_cell` paints nothing visible (or errors).
  Create the tile before painting it.
- **`region_size` is the tile's pixel size in the atlas**, not the grid cell
  size. For a 16×16 sheet tiled into 16×16 cells, both are `[16,16]`; for a
  packed sheet they differ.
- **The texture must already be imported.** `texture_path` points at a
  `res://` Texture2D the editor has imported — it is not a filesystem path.
- **`atlas_coords` are (column, row)** in the sliced grid, origin top-left.
- **`tile_size` is the TileSet's grid**, set once; every tile measures in
  those cells.
- **`tilemap_clear` wipes cells; it does not delete the TileSet.** To
  un-place content without rebuilding the resource, clear and re-set.

### Read back before trusting

`godot_tilemap_get_used_cells(node_path, layer)` lists occupied cells;
`godot_tilemap_get_cell(node_path, position, layer)` reads one;
`godot_tilemap_layers(node_path)` reports the layer count. Use these to verify
a paint or snapshot before a bulk edit.

### Multi-layer

A TileMap has layers; pass `layer` to `set_cell`/`get_cell`. Background,
collision, and decoration are conventionally **separate layers**, not one
layer with different tiles — Godot culls and physics-collides per layer.

---

## The GridMap chain (3D)

Same shape as TileSet, one level simpler — but **cells are indexed by
`item_id`**, and there is no separate `create_cell` step:

```
create_mesh_library → add_mesh_library_item → gridmap_set_cell
    (the palette)        (add a mesh)           (place an item_id)
```

| Step | Tool | What it makes |
|------|------|---------------|
| 1 | `godot_scene_3d_create_mesh_library(node_path, save_path)` | the MeshLibrary on a GridMap |
| 2 | `godot_scene_3d_add_mesh_library_item(mesh_type="BoxMesh", properties={"size": [1,1,1]})` | an item; returns `item_id` |
| 3 | `godot_scene_3d_gridmap_set_cell(node_path, position=[x,y,z], item_id)` | places it |

### Pitfalls

- **A mesh library item needs a mesh** — exactly one of `mesh_type` (primitive
  like `BoxMesh`, configured via `properties`) or `mesh_path` (an imported
  Mesh resource). Passing neither/both is refused.
- **GridMap cell size** is the GridMap's own `cell_size` (default 2m per cell
  in Godot 4 — set it explicitly to avoid surprise scale).
- **`item_id` is not the cell coordinate.** Cells are `position`; the thing at
  a cell is `item_id`. Read one with `godot_scene_3d_gridmap_get_cell(node_path, position)`.

---

## Verify-and-save

Both resources are **mutating** (support `dry_run`) and, when saved as `.tres`,
must be persisted with an explicit save if you edited a shared resource. After
authoring, read back (`get_used_cells` / `gridmap_get_cell`) and confirm the
`.tres` exists.

> Tiles are **content**, not code: keep the atlas texture and `.tres` under
> version control. A scene referencing a missing TileSet loads with blank
> cells, not an error.
