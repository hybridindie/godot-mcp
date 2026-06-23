"""Single source of truth for the toolset-gating protocol text (issue #230).

This protocol — how the agent discovers and enables gated toolsets — was
duplicated across the server ``instructions`` block and the ``toolset_discovery``
prompt, risking drift and paying a per-session token cost. Both now compose from
the constants here.
"""

from __future__ import annotations

DOC_LINKS = (
    "- Tutorial: https://github.com/hybridindie/godot-mcp/blob/main/TUTORIAL.md\n"
    "- Tool contracts: https://github.com/hybridindie/godot-mcp/blob/main/docs/tool-contracts.md\n"
    "- Architecture: https://github.com/hybridindie/godot-mcp/blob/main/docs/architecture.md"
)

GATING_INTRO = (
    "You are connected to a godot-mcp server that gates its tools into categories "
    "called 'toolsets'. Only 'core' (diagnostics, toolset management) and 'inspection' "
    "(read-only project/scene/node reading) are enabled by default. Every other "
    "capability is hidden until you explicitly enable it."
)

MANDATORY_PROTOCOL = (
    "MANDATORY PROTOCOL — follow this order exactly:\n"
    "1. Call get_server_info() for a full capability snapshot "
    "(toolsets, bridge state, troubleshooting).\n"
    "2. Call list_toolsets() to see what is available and which are enabled.\n"
    "3. Call enable_toolset(category) for EVERY category you plan to use.\n"
    "4. Only after enabling can you call the tools in that category.\n\n"
    "WARNING: skip step 3 and EVERY gated tool call fails with "
    "'ToolError: unknown tool'. There is NO fallback."
)

DECISION_TREE = (
    "QUICK DECISION TREE — what do you want to do?\n"
    "- Build/edit scenes, add/move/remove nodes, change properties → scene_edit\n"
    "- Write/attach GDScript, fix parse errors → scripts\n"
    "- Run the game live in the editor (play, inspect, simulate input) → runtime + input\n"
    "- Pause/step/inspect stack at a line → debugger + runtime\n"
    "- Assert a node property meets an expectation → testing + runtime\n"
    "- Apply changes to many nodes at once → batch + scene_edit\n"
    "- Physics bodies, collision shapes, gravity/materials → physics + scene_edit\n"
    "- Register autoloads, create custom resources → resources_edit\n"
    "- Performance, bottlenecks → profiling\n"
    "- Circular deps, unused resources, signal flow → analysis\n"
    "- Export a build for a platform → export\n"
    "- Import textures/audio/models → asset_import"
)

COMMON_TOOLSETS = (
    "Common toolsets you will need:\n"
    "- scene_edit  → create_node, set_node_property, attach_script, save_scene\n"
    "- scripts     → write_script, read_script, get_parse_errors\n"
    "- runtime     → run_and_capture (headless), play_scene (editor)\n"
    "- input       → simulate_action, simulate_key, play_input_sequence\n"
    "- testing     → assert_node_state, run_test_scenario\n"
    "- batch       → batch_set_property, find_nodes_by_type\n"
    "- physics     → setup_physics_body, setup_collision\n"
    "- resources_edit → register_autoload, create_resource\n"
    "- asset_import → import_asset, create_material_from_textures"
)

SERVER_VS_ADDON = (
    "SERVER VS ADDON BOUNDARY:\n"
    "Some tools run in the Python server (list_toolsets, enable_toolset, "
    "get_server_info) and never message Godot. Most tools send commands to the Godot "
    "addon via a WebSocket bridge. 'ToolError: unknown tool' means the toolset is not "
    "enabled OR you confused a server-side tool with an addon tool — call "
    "enable_toolset first."
)

# The full gating protocol, shared verbatim by the server instructions and the
# toolset_discovery prompt. Edit the parts above; both surfaces stay in sync.
TOOLSET_PROTOCOL = "\n\n".join(
    [GATING_INTRO, MANDATORY_PROTOCOL, DECISION_TREE, COMMON_TOOLSETS, SERVER_VS_ADDON]
)

# What the server advertises as its instructions on every session. Leads with the
# protocol, then points at the workflow prompts and docs.
SERVER_INSTRUCTIONS = (
    "WARNING: You MUST follow the steps below or EVERY tool call will fail.\n\n"
    + TOOLSET_PROTOCOL
    + "\n\nDOCUMENTATION:\n"
    + DOC_LINKS
    + "\n\nThis server also exposes workflow prompts (toolset_discovery, build_scene, "
    "play_test, script_edit, debug_scene, troubleshoot) and a diagnostics tool "
    "(get_server_info) that returns tool counts, bridge state, active scene, and "
    "common errors with fixes."
)
