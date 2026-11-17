# Demo animation — provenance

`godot-mcp-demo.gif` / `.mp4` / `-poster.png` show a **real session**: OpenCode
driving a live Godot 4.7.1 editor through `godot-mcp` over its HTTP transport and
the WebSocket bridge. Nothing in the editor pane is mocked, scripted, or
composited — the scene tree, the 2D view, and the addon's MCP dock are the editor.

## How it was shot

| Piece | What it was |
|---|---|
| Editor | Godot 4.7.1 (Linux, Mesa llvmpipe), `examples/vampire` opened on `main.tscn`, addon connected to `ws://127.0.0.1:9091` |
| Server | `godot-editor-mcp` with `GODOT_MCP_TRANSPORT=http` (port 9090) — one persistent bridge for the whole take |
| Agent | `opencode run --standalone --format json --auto "<prompt>"`, model `ollama-cloud/deepseek-v4.1-flash` |
| Capture | Two virtual X displays (`Xvfb`): the editor at 1200×1080 and a transcript page at 720×1080, recorded together with `ffmpeg -f x11grab` and stacked side by side |
| Transcript | Rendered live from the session's own JSON event stream (tool name, arguments, result) — not hand-written captions |

The prompt, verbatim:

```text
In the open main scene, add a spinning gem: a Node2D named Gem at (420, -40)
with a diamond Polygon2D child and a gem.gd script that rotates and bobs it.
Enable only the toolsets you need, then save the scene and confirm the scene
tree. Don't read other scripts and don't run the game.
```

What the session actually did, in order: `godot_get_server_info` →
`godot_list_toolsets` → `godot_enable_toolset(scene_edit, scripts)` →
`godot_inspection_get_scene_tree` → `godot_scene_edit_create_node` →
`godot_scripts_write` → `godot_scene_edit_set_node_property` ×3 →
`godot_scene_edit_create_node` → `godot_scene_edit_attach_script` →
`godot_scripts_get_parse_errors` → `godot_scene_edit_save_scene` →
`godot_inspection_get_scene_tree` → property read-backs ×5.

## Honest caveats

- **Speed.** The GIF is 1.2× the recorded time (13 s, 12 fps, 1200×675); the MP4 is
  real time (16 s, 1600×900), trimmed only for the pre-session lead-in.
- **One rig-only tweak.** The addon's status dock keeps 50 recent commands, and
  that list's minimum height squeezes the 2D viewport in a small window. The demo
  copy of the addon caps it at 8. The shipped addon is unchanged.
- **The transcript pane is a rendering.** It is built from the session's real JSON
  events in real time, but it is a styled view, not a terminal recording — so its
  font, spacing and colours are chosen for legibility at 1200 px.
- This take has no failed calls. Earlier ones did (a wrong tool namespace), and
  they were left in when they happened — the recovery is part of the story.

## Re-shooting

The rig lived outside the repo (`/tmp/opencode/demo`: `rig.sh`, `reset_demo.sh`,
`run_session.py`, `take.sh`, `web/index.html`). Re-shoot when the tool surface or
the README's claim changes, not on a schedule — the point is that the tools in the
transcript still exist.
