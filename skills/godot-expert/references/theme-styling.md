# Theme & Control Styling

Godot styling has **two layers**, and confusing them is the #1 reason a style
"doesn't apply":

1. **Theme** — a `Theme` resource bound to a Control; holds colors, font sizes,
   styleboxes, constants, fonts, icons keyed by **item name**.
2. **Local override** — a per-node override on a single Control; wins over the
   bound theme.

The `theme_ui` toolset writes both. This is the MCP-side of the engine rule
"local overrides take precedence over the theme."

## Two ways to set a value

```
# Whole-theme (shapes every Control that uses this theme)
godot_theme_ui_create(node_path, save_path="res://theme.tres")
godot_theme_ui_set_stylebox(node_path, name="panel", stylebox_type="StyleBoxFlat",
                            properties={"bg_color": "#1b1e29", "corner_radius_top_left": 8})

# Per-node override (this Control only; beats the theme)
godot_theme_ui_set_color(node_path, name="font_color", color="#ffd166")
godot_theme_ui_set_font_size(node_path, name="font_size", size=22)
```

| Tool | Sets |
|------|------|
| `godot_theme_ui_create(node_path, save_path)` | a Theme on a Control (saved `.tres` if `save_path`, else embedded) |
| `godot_theme_ui_set_color(node_path, name, color)` | a theme **color** item (e.g. `font_color`) |
| `godot_theme_ui_set_font_size(node_path, name, size)` | a theme **font_size** item |
| `godot_theme_ui_set_stylebox(node_path, name, stylebox_type, properties)` | a theme **stylebox** item |
| `godot_theme_ui_get_node_overrides(node_path)` | read overrides back (colors / font_sizes / styleboxes) |

## Pitfalls

- **Item `name` is type-defined, not arbitrary.** `font_color` works on a
  Button/Label because those types declare it. Setting `font_color` on a
  Control that doesn't declare that item does nothing useful. Check the
  control's item names before guessing.
- **StyleBox `name` is the *state*.** A Button styles `normal`, `hover`,
  `pressed`, `disabled`, `focus` — separately. Styling only `normal` leaves
  hover/pressed unstyled (the default look bleeding through). Style each state.
- **`stylebox_type` matters.** `StyleBoxFlat` (solid/rounded/bordered),
  `StyleBoxTexture` (9-slice image), `StyleBoxEmpty` (no draw), `StyleBoxLine`.
  `properties` are that type's fields — `bg_color`/`border_width_all`/
  `corner_radius_*` for Flat, a texture + margins for Texture.
- **Colors accept HTML or array:** `"#ff8800"` or `[r,g,b,a]`.
- **A saved theme is shared; an embedded one is scene-local.** Pass
  `save_path` for a theme reused across scenes; omit it to keep the theme
  inside the scene.
- **Overrides don't propagate.** Setting `font_color` on one Label doesn't
  affect siblings — that's the theme's job, or use a type variation.

## Sizing: anchors, not positions

The engine rule (see `references/ui-hud.md`) is that Controls lay out by
**anchors**, not by setting `position`/`size` directly. A styled panel that
"disappears" is usually an anchor/layout `size` of zero, not a color problem.
Set anchors first, then style.

## Read-back

`godot_theme_ui_get_node_overrides(node_path)` returns the node's
**local overrides** — colors, font sizes, styleboxes — so you can confirm what
was set (and snapshot before editing). It reports overrides that apply, not the
full resolved theme; inherited theme values won't show.
