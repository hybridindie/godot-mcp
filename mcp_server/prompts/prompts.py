"""MCP prompts (``@mcp.prompt()``) — instruction templates for the agent.

Prompts tell the LLM which tools/resources to use in what order. They do not act;
the server returns instructions as messages that the agent consumes. Typed,
documented arguments let agents parameterize workflows.

Issue #12 — shipped as part of the tutorial & client-comprehensibility work.
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.prompts import Message

from mcp_server.bridge import Bridge
from mcp_server.prompts.completion import register_completion
from mcp_server.toolset_protocol import TOOLSET_PROTOCOL


def _as_arg(text: str) -> str:
    """Render a string as a valid quoted literal for a tool-call example.

    ``repr`` picks safe quoting (switching to double quotes when the value
    contains a single quote), so interpolated user values never break the
    example syntax we teach the model.
    """
    return repr(text)


def _as_value(value: str) -> str:
    """Render a batch ``value`` as it should appear in a call.

    JSON-shaped values (objects, arrays, numbers, booleans, null) render as-is;
    anything else is treated as a string literal and quoted — so a color like
    ``#ff0000`` becomes ``'#ff0000'`` rather than the invalid bare ``#ff0000``.
    """
    v = value.strip()
    if v[:1] in "{[" or v.lower() in {"true", "false", "null"}:
        return v
    try:
        float(v)
    except ValueError:
        return _as_arg(v)
    return v


def register_prompts(mcp: FastMCP, bridge: Bridge) -> list[str]:
    """Register all workflow prompts on the server.

    Returns the registered prompt names so the caller can advertise them without
    introspecting FastMCP internals (#231/#233). Each registrant returns the name
    it registered, so the list stays in lockstep with the actual prompts.

    Also registers the argument-completion handler (#314) — registering it here
    advertises the completions capability at negotiation.
    """
    register_completion(mcp, bridge)
    return [
        _register_toolset_discovery(mcp),
        _register_build_scene(mcp),
        _register_play_test(mcp),
        _register_script_edit(mcp),
        _register_debug_scene(mcp),
        _register_troubleshoot(mcp),
        _register_author_resource(mcp),
        _register_export_build(mcp),
        _register_batch_refactor(mcp),
    ]


def _register_toolset_discovery(mcp: FastMCP) -> str:
    @mcp.prompt(
        name="toolset_discovery",
        description=(
            "Instructs the agent how to discover and enable gated toolsets. "
            "ALWAYS use this prompt at the start of every session before any scene editing, "
            "script writing, runtime testing, or batch operations."
        ),
    )
    def toolset_discovery() -> list[Message]:
        """Teach the agent the toolset gating system so it never fails to find tools."""
        # Single-sourced from mcp_server.toolset_protocol so this prompt and the
        # server instructions can never drift apart (issue #230).
        return [Message(role="user", content=TOOLSET_PROTOCOL)]

    return "toolset_discovery"


def _register_build_scene(mcp: FastMCP) -> str:
    @mcp.prompt(
        name="build_scene",
        description=(
            "Step-by-step workflow for creating a new scene with nodes, scripts, and "
            "collision shapes using the scene_edit and scripts toolsets."
        ),
    )
    def build_scene(
        scene_path: str = "res://scenes/main.tscn",
        root_type: str = "Node2D",
    ) -> list[Message]:
        """Instruct the agent how to scaffold a scene from scratch."""
        return [
            Message(
                role="user",
                content=(
                    f"Build a new Godot scene step by step:\n\n"
                    f"SCENE: {scene_path} with root type {root_type}\n\n"
                    "Step 1 — Enable the required toolsets:\n"
                    "  godot_enable_toolset('scene_edit')\n"
                    "  godot_enable_toolset('scripts')\n"
                    "  godot_enable_toolset('physics')  [if you need collision]\n\n"
                    "Step 2 — Create or open the scene:\n"
                    f"  godot_scene_edit_create_scene(scene_path='{scene_path}', "
                    f"root_type='{root_type}')\n"
                    "  OR godot_scene_edit_open_scene(scene_path='...') if it already exists\n\n"
                    "Step 3 — Add nodes with godot_scene_edit_create_node(parent_path, node_type, "
                    "node_name):\n"
                    "  - parent_path='.' is the scene root\n"
                    "  - Set position with godot_scene_edit_set_node_property(\n"
                    "      node_path, 'position', {'x': 0, 'y': 0})\n\n"
                    "Step 4 — Attach scripts:\n"
                    "  - godot_scripts_write(script_path='res://scripts/my_script.gd', "
                    "content='...')\n"
                    "  - godot_scene_edit_attach_script(node_path='./MyNode', "
                    "script_path='res://scripts/my_script.gd')\n\n"
                    "Step 5 — Add collision (optional):\n"
                    "  - godot_physics_setup_collision(\n"
                    "      node_path='./MyNode',\n"
                    "      collision_node_type='CollisionShape2D',\n"
                    "      shape_type='CircleShape2D',\n"
                    "      properties={'radius': 32})\n\n"
                    "Step 6 — Save and verify:\n"
                    "  - godot_scene_edit_save_scene()\n"
                    "  - godot_inspection_get_scene_tree(max_depth=2) to inspect what you built\n"
                    "  - godot_scripts_get_parse_errors() to check scripts compile\n\n"
                    "SAFETY REMINDER:\n"
                    "- mutating tools accept dry_run=True to preview without changing anything\n"
                    "- destructive tools (godot_scene_edit_delete_node, "
                    "godot_scene_edit_reload_scene) require confirm=True"
                ),
            ),
        ]

    return "build_scene"


def _register_play_test(mcp: FastMCP) -> str:
    @mcp.prompt(
        name="play_test",
        description=(
            "Workflow for live play-testing inside the Godot editor: play a scene, "
            "inspect the running game, simulate input, assert state, and stop."
        ),
    )
    def play_test(
        scene_path: str = "res://scenes/main.tscn",
    ) -> list[Message]:
        """Instruct the agent how to drive and inspect a live game session."""
        return [
            Message(
                role="user",
                content=(
                    f"Play-test the scene '{scene_path}' live inside the Godot editor. "
                    "Godot must be open with the addon enabled.\n\n"
                    "Step 1 — Enable toolsets:\n"
                    "  godot_enable_toolset('runtime')\n"
                    "  godot_enable_toolset('input')\n"
                    "  godot_enable_toolset('testing')\n"
                    "  godot_enable_toolset('resources_edit')\n\n"
                    "Step 2 — Ensure the runtime probe is registered:\n"
                    "  godot_inspection_get_project_info() → check autoloads for "
                    "'MCPRuntimeProbe'\n"
                    "  If missing: godot_resources_edit_register_autoload(\n"
                    "      name='MCPRuntimeProbe',\n"
                    "      path='res://addons/godot_mcp/mcp_runtime_probe.gd'\n"
                    "  )\n\n"
                    "Step 3 — Play the scene from the editor:\n"
                    f"  godot_runtime_play_scene(scene_path='{scene_path}')\n"
                    "  Confirm with godot_runtime_is_playing() → {'playing': true}\n\n"
                    "Step 4 — Inspect the live game:\n"
                    "  godot_runtime_get_game_scene_tree() → see the running node hierarchy\n"
                    "  godot_runtime_monitor_property(\n"
                    "      node_path='/root/Main/Player',\n"
                    "      property='position',\n"
                    "      samples=30)\n"
                    "  godot_runtime_get_property_samples() → collect the sampled values\n"
                    "  godot_runtime_find_ui_elements(name_contains='Score') → locate UI "
                    "controls\n\n"
                    "Step 5 — Simulate input:\n"
                    "  godot_input_simulate_action(action='ui_right', pressed=true)  # hold\n"
                    "  godot_input_simulate_action(action='ui_right', pressed=false) # release\n"
                    "  godot_input_simulate_key(key='Space', pressed=true)\n"
                    "  godot_input_play_sequence(events=[...], delay_ms=100)  # replay macro\n\n"
                    "Step 6 — Assert state:\n"
                    "  godot_testing_assert_node_state(\n"
                    "      node_path='/root/Main/GameManager',\n"
                    "      property='coin_count',\n"
                    "      expected=3,\n"
                    "      op='>='\n"
                    "  )\n\n"
                    "Step 7 — Stop:\n"
                    "  godot_runtime_stop_scene()\n\n"
                    "IMPORTANT DISTINCTION:\n"
                    "- godot_runtime_play_scene()  → editor play session (live, inspectable, needs "
                    "probe)\n"
                    "- godot_runtime_run_and_capture() → headless subprocess (no editor, no live "
                    "interaction)"
                ),
            ),
        ]

    return "play_test"


def _register_script_edit(mcp: FastMCP) -> str:
    @mcp.prompt(
        name="script_edit",
        description=(
            "Workflow for authoring GDScript: write a script, attach it to a node, "
            "check for parse errors, and patch it in place."
        ),
    )
    def script_edit(
        script_path: str = "res://scripts/my_script.gd",
        node_path: str = "./MyNode",
    ) -> list[Message]:
        """Instruct the agent how to create, attach, and iterate on a GDScript file."""
        return [
            Message(
                role="user",
                content=(
                    f"Write and attach a GDScript to a node step by step.\n\n"
                    f"SCRIPT: {script_path}\n"
                    f"NODE:   {node_path}\n\n"
                    "Step 1 — Enable the scripts toolset:\n"
                    "  godot_enable_toolset('scripts')\n\n"
                    "Step 2 — Write the script:\n"
                    f"  godot_scripts_write(script_path='{script_path}', content='extends "
                    f"Node\n...')\n\n"
                    "Step 3 — Check for parse errors (headless, no editor needed):\n"
                    f"  godot_scripts_get_parse_errors(script_path='{script_path}')\n"
                    "  Fix any errors before attaching.\n\n"
                    "Step 4 — Attach to the node:\n"
                    "  godot_enable_toolset('scene_edit')\n"
                    f"  godot_scene_edit_attach_script(node_path='{node_path}', "
                    f"script_path='{script_path}')\n\n"
                    "Step 5 — Iterate with patches (no full rewrite):\n"
                    f"  godot_scripts_patch(\n"
                    f"      script_path='{script_path}',\n"
                    f"      find='old_code_here',\n"
                    f"      replace='new_code_here'\n"
                    f"  )\n\n"
                    "Step 6 — Verify in-editor (optional):\n"
                    "  godot_scripts_get_for_node(\n"
                    f"      node_path='{node_path}') → read back the attached script\n"
                    "  godot_scripts_get_parse_errors(\n"
                    f"      script_path='{script_path}') → final parse check\n\n"
                    "TIP: Use dry_run=True on any mutating tool to preview before committing."
                ),
            ),
        ]

    return "script_edit"


def _register_debug_scene(mcp: FastMCP) -> str:
    @mcp.prompt(
        name="debug_scene",
        description=(
            "Systematic debugging workflow for a Godot scene or script that is failing. "
            "Uses godot_health_check, godot_scripts_get_parse_errors, "
            "godot_runtime_run_and_capture, and godot_analysis_analyze_signal_flow "
            "to identify root causes and suggest fixes."
        ),
    )
    def debug_scene(
        scene_path: str = "",
        script_path: str = "",
    ) -> list[Message]:
        """Instruct the agent how to diagnose and fix errors in a scene or script."""
        scene_clause = f" (scene: {scene_path})" if scene_path else ""
        script_clause = f" (script: {script_path})" if script_path else ""
        return [
            Message(
                role="user",
                content=(
                    f"Debug a failing Godot scene or script{scene_clause}{script_clause}. "
                    "Follow this systematic checklist.\n\n"
                    "TOOLSETS TO ENABLE (before any debug steps):\n"
                    "  godot_enable_toolset('scripts')\n"
                    "  godot_enable_toolset('runtime')\n"
                    "  godot_enable_toolset('analysis')\n"
                    "  godot_enable_toolset('inspection')  [already on by default]\n\n"
                    "PHASE 1 — Quick Health Check\n"
                    "  godot_debug_workflow()\n"
                    "  → Returns bridge state, scene tree, headless run "
                    "errors, and suggestions in one call.\n"
                    "  godot_inspection_get_project_info()\n"
                    "  → Returns project name, Godot version, autoloads, and main scene.\n"
                    "  godot_inspection_get_scene_tree(max_depth=2)\n"
                    "  → Spot-check the scene structure for obvious problems.\n\n"
                    "PHASE 2 — Script Analysis (if a script is involved)\n"
                    f"  godot_scripts_get_parse_errors(script_path='{script_path or 'res://scripts/my_script.gd'}')"  # noqa: E501
                    "\n  → Fix any parse errors (syntax, missing parentheses, "  # noqa: E501
                    "undefined variables).\n\n"
                    "PHASE 3 — Scene Structure Check\n"
                    "  godot_inspection_get_scene_tree(max_depth=-1)\n"
                    "  godot_inspection_get_node_properties(node_path='./Player')  "
                    "[or the failing node]\n"
                    "  → Verify nodes exist, scripts are attached, and "
                    "property values are sane.\n\n"
                    "PHASE 4 — Signal Flow Inspection\n"
                    f"  godot_analysis_analyze_signal_flow(scene='{scene_path or 'res://scenes/main.tscn'}')"  # noqa: E501
                    "\n  → Look for disconnected signals, wrong method "  # noqa: E501
                    "names, or missing target nodes.\n\n"
                    "PHASE 5 — Headless Run with Logs\n"
                    f"  godot_runtime_run_and_capture(scene='{scene_path or ''}', "
                    f"timeout_seconds=5)\n"
                    "  → Read errors[] and warnings[] for runtime failures.\n\n"
                    "PHASE 6 — Live Debug (if the game runs but behaves wrong)\n"
                    "  godot_runtime_play_scene(scene_path='...')\n"
                    "  godot_runtime_get_game_scene_tree() → verify runtime node hierarchy\n"
                    "  godot_runtime_monitor_property(\n"
                    "      node_path='/root/Main/Player',\n"
                    "      property='position',\n"
                    "      samples=30)\n"
                    "  → Check if values change as expected.\n\n"
                    "PHASE 7 — Static Project Analysis\n"
                    "  godot_analysis_detect_circular_dependencies() → script A loads B loads A?\n"
                    "  godot_analysis_find_unused_resources() → missing textures/sounds that crash "
                    "on load?\n"
                    "  godot_analysis_project_stats() → identify the most complex scenes\n\n"
                    "COMMON FIXES:\n"
                    "- 'Invalid get index' → the node path changed; verify with "
                    "godot_inspection_get_scene_tree().\n"
                    "- 'Method not found' → signal target method was renamed or deleted.\n"
                    "- 'Null instance' → a node was freed (queue_free) but "
                    "something still references it.\n"
                    "- 'Could not load resource' → file path is wrong or the file was deleted.\n"
                    "- 'Parse Error' → fix the line/column reported by "
                    "godot_scripts_get_parse_errors().\n"
                    "- 'Division by zero' → check divisor values with "
                    "godot_runtime_monitor_property().\n\n"
                    "SAFETY: Every mutating tool accepts dry_run=True to preview fixes.\n"
                    "DOCUMENTATION: https://github.com/hybridindie/godot-mcp/blob/main/TUTORIAL.md"
                ),
            ),
        ]

    return "debug_scene"


def _register_troubleshoot(mcp: FastMCP) -> str:
    @mcp.prompt(
        name="troubleshoot",
        description=(
            "Diagnostic playbook for common godot-mcp failures. Returns a checklist "
            "the agent can follow to identify and fix bridge, toolset, scene, and runtime problems."
        ),
    )
    def troubleshoot() -> list[Message]:
        """Give the agent a structured debugging checklist."""
        return [
            Message(
                role="user",
                content=(
                    "Something went wrong. Follow this diagnostic checklist in order.\n\n"
                    "STEP 1 — Check server health:\n"
                    "  godot_get_server_info()\n"
                    "  → Look at 'bridge.connected', 'active_scene', and 'next_steps'.\n\n"
                    "STEP 2 — If bridge is disconnected:\n"
                    "  - Godot must be running with the addon enabled.\n"
                    "  - Check Project Settings → Plugins → godot_mcp → Enable.\n"
                    "  - Check the status dock at the bottom of Godot.\n"
                    "  - Verify port 9080 is not blocked by another process.\n"
                    "  - Try godot_health_check() to see the bridge_url the server expects.\n\n"
                    "STEP 3 — If you get 'ToolError: unknown tool':\n"
                    "  - Call godot_list_toolsets() → confirm the toolset is disabled.\n"
                    "  - Call godot_enable_toolset('scene_edit') [or relevant category].\n"
                    "  - Retry the tool call.\n\n"
                    "STEP 4 — If you get PRECONDITION_FAILED:\n"
                    "  - required=active_scene → open/create a .tscn scene first.\n"
                    "  - required=confirm → add confirm=True (or dry_run=True to preview).\n"
                    "  - required=play_session → call godot_runtime_play_scene() before live "
                    "tools.\n"
                    "  - required=runtime_probe → register MCPRuntimeProbe as autoload.\n"
                    "  - required=bridge_connected → see Step 2.\n"
                    "  - required=godot_version → upgrade Godot to 4.4+.\n\n"
                    "STEP 5 — If scripts fail to parse:\n"
                    "  godot_scripts_get_parse_errors(script_path='res://scripts/my.gd')\n"
                    "  → Fix reported line/column, then re-run.\n\n"
                    "STEP 6 — If the game crashes on play:\n"
                    "  - godot_runtime_run_and_capture(scene='res://scenes/main.tscn', "
                    "timeout_seconds=5)\n"
                    "  → Check 'errors' and 'warnings' in the result.\n"
                    "  - Look for null references, missing nodes, or "
                    "signal connection failures.\n\n"
                    "STEP 7 — If live input simulation doesn't work:\n"
                    "  - Confirm godot_runtime_play_scene() is running (godot_runtime_is_playing() "
                    "→ true).\n"
                    "  - Confirm MCPRuntimeProbe is in autoloads "
                    "(godot_inspection_get_project_info()).\n"
                    "  - Check the live scene tree includes the target "
                    "node (godot_runtime_get_game_scene_tree()).\n\n"
                    "DOCUMENTATION:\n"
                    "- Tutorial: https://github.com/hybridindie/godot-mcp/blob/main/TUTORIAL.md\n"
                    "- Tool specs: "
                    "https://github.com/hybridindie/godot-mcp/blob/main/docs/tool-contracts.md\n"
                    "- Architecture: "
                    "https://github.com/hybridindie/godot-mcp/blob/main/docs/architecture.md"
                ),
            ),
        ]

    return "troubleshoot"


# Per-kind authoring recipes for the author_resource prompt. Each names the toolset
# to enable and the tool sequence; ``{save_path}`` is filled per call. Keep the tool
# names in sync with the exposed godot_<toolset>_<action> surface.
_AUTHOR_RESOURCE_RECIPES = {
    "tileset": (
        "Author a TileSet (the resource that makes cells placeable on a TileMapLayer):\n\n"
        "Step 1 — Enable the toolset:\n"
        "  godot_enable_toolset('tilemap')\n\n"
        "Step 2 — Create the TileSet (save it and/or assign to a node):\n"
        "  godot_tilemap_create_tileset(save_path='{save_path}', tile_size=[16, 16])\n"
        "  (or node_path='./TileMapLayer' to assign it in-scene)\n\n"
        "Step 3 — Add an atlas source from an imported texture:\n"
        "  godot_tilemap_add_tileset_atlas_source(\n"
        "      tileset_path='{save_path}',\n"
        "      texture_path='res://art/tiles.png', region_size=[16, 16])\n"
        "  → returns source_id\n\n"
        "Step 4 — Create the individual tiles you want to place:\n"
        "  godot_tilemap_create_tile(\n"
        "      tileset_path='{save_path}', source_id=<id>, atlas_coords=[0, 0])\n\n"
        "Step 5 — Place tiles (needs a TileMapLayer in the open scene):\n"
        "  godot_tilemap_set_cell(node_path='./TileMapLayer', coords=[0, 0],\n"
        "      source_id=<id>, atlas_coords=[0, 0])"
    ),
    "meshlibrary": (
        "Author a MeshLibrary (the resource a GridMap places cells from):\n\n"
        "Step 1 — Enable the toolset:\n"
        "  godot_enable_toolset('scene_3d')\n\n"
        "Step 2 — Create the MeshLibrary:\n"
        "  godot_scene_3d_create_mesh_library(save_path='{save_path}')\n\n"
        "Step 3 — Add an item per mesh (from an imported mesh/scene):\n"
        "  godot_scene_3d_add_mesh_library_item(\n"
        "      library_path='{save_path}', mesh_path='res://art/wall.obj')\n"
        "  → returns the item id\n\n"
        "Step 4 — Place cells (needs a GridMap in the open scene):\n"
        "  godot_scene_3d_gridmap_set_cell(\n"
        "      node_path='./GridMap', cell=[0, 0, 0], item=<id>)"
    ),
    "theme": (
        "Author a Theme (shared styling for Control nodes):\n\n"
        "Step 1 — Enable the toolset:\n"
        "  godot_enable_toolset('theme_ui')\n\n"
        "Step 2 — Create the Theme (assign to a Control; save to share it):\n"
        "  godot_theme_ui_create(node_path='./UI', save_path='{save_path}')\n\n"
        "Step 3 — Set styling on nodes that use it:\n"
        "  godot_theme_ui_set_color(node_path='./UI/Label', name='font_color', "
        "color='#ffffff')\n"
        "  godot_theme_ui_set_font_size(node_path='./UI/Label', name='font_size', size=24)\n"
        "  godot_theme_ui_set_stylebox(node_path='./UI/Panel', name='panel', ...)"
    ),
    "shader": (
        "Author a Shader and apply it to a node (use a .gdshader save_path):\n\n"
        "Step 1 — Enable the toolset:\n"
        "  godot_enable_toolset('shader')\n\n"
        "Step 2 — Create the .gdshader file:\n"
        "  godot_shader_create(shader_path='{save_path}', code='...')\n\n"
        "Step 3 — Wrap it in a ShaderMaterial and assign it:\n"
        "  godot_shader_assign_material(node_path='./Sprite2D',\n"
        "      shader_path='{save_path}')\n\n"
        "Step 4 — Tune uniforms:\n"
        "  godot_shader_set_param(node_path='./Sprite2D', name='intensity', value=0.5)"
    ),
    "custom": (
        "Author a custom/built-in Resource (.tres) directly:\n\n"
        "Step 1 — Enable the toolset:\n"
        "  godot_enable_toolset('resources_edit')\n\n"
        "Step 2 — Create the resource of the type you need:\n"
        "  godot_resources_edit_create_resource(\n"
        "      type='CurveTexture', resource_path='{save_path}', properties={{}})\n\n"
        "Step 3 — Edit individual properties later:\n"
        "  godot_resources_edit_set_resource_property(\n"
        "      resource_path='{save_path}', property='width', value=256)"
    ),
}


def _register_author_resource(mcp: FastMCP) -> str:
    kinds = ", ".join(sorted(_AUTHOR_RESOURCE_RECIPES))

    @mcp.prompt(
        name="author_resource",
        description=(
            "Step-by-step workflow for authoring a Godot resource and the tools to use. "
            f"Set resource_kind to one of: {kinds}. Covers TileSet, MeshLibrary, Theme, "
            "Shader, and custom .tres resources."
        ),
    )
    def author_resource(
        resource_kind: str = "tileset",
        save_path: str = "res://resources/new_resource.tres",
    ) -> list[Message]:
        """Instruct the agent how to author a resource of the requested kind."""
        recipe = _AUTHOR_RESOURCE_RECIPES.get(resource_kind.lower().strip())
        if recipe is None:
            body = (
                f"Unknown resource_kind '{resource_kind}'. Choose one of: {kinds}.\n"
                "Re-invoke author_resource with a supported resource_kind."
            )
        else:
            body = recipe.format(save_path=save_path) + (
                "\n\nSAFETY REMINDER:\n"
                "- Every step above is a mutating tool; add dry_run=True to preview first.\n"
                "- Verify with godot_inspection tools (e.g. read the saved .tres) when done."
            )
        return [Message(role="user", content=body)]

    return "author_resource"


def _register_export_build(mcp: FastMCP) -> str:
    @mcp.prompt(
        name="export_build",
        description=(
            "Workflow for exporting a project build for a target platform using the "
            "export toolset: discover presets, check templates, export, verify."
        ),
    )
    def export_build(
        preset: str = "",
        output_path: str = "res://build/game",
    ) -> list[Message]:
        """Instruct the agent how to export a build for a platform preset."""
        target = preset or "<your preset, e.g. 'Windows Desktop' / 'Linux/X11' / 'Web'>"
        return [
            Message(
                role="user",
                content=(
                    f"Export a build to '{output_path}' using preset: {target}\n\n"
                    "Step 1 — Enable the toolset:\n"
                    "  godot_enable_toolset('export')\n\n"
                    "Step 2 — Discover the presets defined in export_presets.cfg:\n"
                    "  godot_export_list_presets()\n"
                    "  → Match the preset name exactly (it is case-sensitive).\n\n"
                    "Step 3 — Confirm export templates are installed for the target:\n"
                    "  godot_export_get_info()\n"
                    "  → If templates are missing, install them in Godot "
                    "(Editor → Manage Export Templates) before exporting.\n\n"
                    "Step 4 — Export (runs Godot headless; can be slow):\n"
                    f"  godot_export_project(preset={_as_arg(target)}, "
                    f"output_path={_as_arg(output_path)},\n"
                    "      debug=False, timeout_seconds=300)\n\n"
                    "Step 5 — Verify the result:\n"
                    "  → Check exit_code == 0 and that 'errors' is empty.\n"
                    "  → A non-zero code with no errors usually means a missing template "
                    "or a bad preset name (re-check Step 2/3)."
                ),
            ),
        ]

    return "export_build"


def _register_batch_refactor(mcp: FastMCP) -> str:
    @mcp.prompt(
        name="batch_refactor",
        description=(
            "Workflow for changing a property across many nodes safely with the batch "
            "toolset: find targets, preview with dry_run, apply, verify."
        ),
    )
    def batch_refactor(
        node_type: str = "Node",
        property: str = "",
        value: str = "",
    ) -> list[Message]:
        """Instruct the agent how to apply a property change across many nodes."""
        prop = property or "modulate"
        val = _as_value(value) if value.strip() else "<value, JSON-shaped for the type>"
        return [
            Message(
                role="user",
                content=(
                    f"Set {_as_arg(prop)} = {val} on every {node_type} in scope, safely.\n\n"
                    "Step 1 — Enable the toolset (add scene_edit if you also create/move "
                    "nodes):\n"
                    "  godot_enable_toolset('batch')\n\n"
                    "Step 2 — Find the targets first, so you know the blast radius:\n"
                    f"  godot_batch_find_nodes_by_type(node_type={_as_arg(node_type)})\n\n"
                    "Step 3 — PREVIEW with dry_run before changing anything:\n"
                    f"  godot_batch_set_property(property={_as_arg(prop)}, value={val},\n"
                    f"      node_type={_as_arg(node_type)}, dry_run=True)\n"
                    "  → Review 'applied' and 'skipped' (nodes lacking the property).\n\n"
                    "Step 4 — Apply once the plan looks right (one undoable action):\n"
                    f"  godot_batch_set_property(property={_as_arg(prop)}, value={val},\n"
                    f"      node_type={_as_arg(node_type)})\n\n"
                    "Step 5 — For a project-wide change across scene files, use:\n"
                    "  godot_batch_cross_scene_set_property(...)  (also supports dry_run)\n\n"
                    "VALUE SHAPES: Vector2/3 as {'x':1,'y':2} or [1,2]; Color as "
                    "{'r':1,'g':0,'b':0,'a':1} or '#ff0000'; primitives as-is."
                ),
            ),
        ]

    return "batch_refactor"
