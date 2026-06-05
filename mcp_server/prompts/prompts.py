"""MCP prompts (``@mcp.prompt()``) — instruction templates for the agent.

Prompts tell the LLM which tools/resources to use in what order. They do not act;
the server returns instructions as messages that the agent consumes. Typed,
documented arguments let agents parameterize workflows.

Issue #12 — shipped as part of the tutorial & client-comprehensibility work.
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.prompts import Message


def register_prompts(mcp: FastMCP) -> None:
    """Register all workflow prompts on the server."""
    _register_toolset_discovery(mcp)
    _register_build_scene(mcp)
    _register_play_test(mcp)
    _register_script_edit(mcp)
    _register_debug_scene(mcp)
    _register_troubleshoot(mcp)


def _register_toolset_discovery(mcp: FastMCP) -> None:
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
        return [
            Message(
                role="user",
                content=(
                    "You are working with a godot-mcp server that gates its tools into "
                    "categories called 'toolsets'. Only 'core' (diagnostics, toolset "
                    "management) and 'inspection' (read-only project/scene/node reading) "
                    "are enabled by default. Every other capability is hidden until you "
                    "explicitly enable it.\n\n"
                    "MANDATORY PROTOCOL — follow this order exactly:\n"
                    "1. Call list_toolsets() to see what is available and which are enabled.\n"
                    "2. Call enable_toolset(category) for every category you plan to use.\n"
                    "3. Only after enabling can you call the tools in that category.\n\n"
                    "Common toolsets you will need:\n"
                    "- scene_edit  → create_node, set_node_property, attach_script, save_scene\n"
                    "- scripts     → write_script, read_script, get_parse_errors\n"
                    "- runtime     → run_and_capture (headless), play_scene (editor)\n"
                    "- input       → simulate_action, simulate_key, play_input_sequence\n"
                    "- testing     → assert_node_state, run_test_scenario\n"
                    "- batch       → batch_set_property, find_nodes_by_type\n"
                    "- physics     → setup_physics_body, setup_collision\n"
                    "- resources_edit → register_autoload, create_resource\n\n"
                    "If you try to call a tool and get 'ToolError: unknown tool', the toolset "
                    "is not enabled. Call enable_toolset first."
                ),
            ),
        ]


def _register_build_scene(mcp: FastMCP) -> None:
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
                    "  enable_toolset('scene_edit')\n"
                    "  enable_toolset('scripts')\n"
                    "  enable_toolset('physics')  [if you need collision]\n\n"
                    "Step 2 — Create or open the scene:\n"
                    f"  create_scene(scene_path='{scene_path}', root_type='{root_type}')\n"
                    "  OR open_scene(scene_path='...') if it already exists\n\n"
                    "Step 3 — Add nodes with create_node(parent_path, node_type, node_name):\n"
                    "  - parent_path='.' is the scene root\n"
                    "  - Set position with set_node_property(\n"
                    "      node_path, 'position', {'x': 0, 'y': 0})\n\n"
                    "Step 4 — Attach scripts:\n"
                    "  - write_script(script_path='res://scripts/my_script.gd', content='...')\n"
                    "  - attach_script(node_path='./MyNode', script_path='res://scripts/my_script.gd')\n\n"
                    "Step 5 — Add collision (optional):\n"
                    "  - setup_collision(\n"
                    "      node_path='./MyNode',\n"
                    "      collision_node_type='CollisionShape2D',\n"
                    "      shape_type='CircleShape2D',\n"
                    "      properties={'radius': 32})\n\n"
                    "Step 6 — Save and verify:\n"
                    "  - save_scene()\n"
                    "  - get_scene_tree(max_depth=2) to inspect what you built\n"
                    "  - get_parse_errors() to check scripts compile\n\n"
                    "SAFETY REMINDER:\n"
                    "- mutating tools accept dry_run=True to preview without changing anything\n"
                    "- destructive tools (delete_node, reload_scene) require confirm=True"
                ),
            ),
        ]


def _register_play_test(mcp: FastMCP) -> None:
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
                    "  enable_toolset('runtime')\n"
                    "  enable_toolset('input')\n"
                    "  enable_toolset('testing')\n"
                    "  enable_toolset('resources_edit')\n\n"
                    "Step 2 — Ensure the runtime probe is registered:\n"
                    "  get_project_info() → check autoloads for 'MCPRuntimeProbe'\n"
                    "  If missing: register_autoload(\n"
                    "      name='MCPRuntimeProbe',\n"
                    "      path='res://addons/godot_mcp/mcp_runtime_probe.gd'\n"
                    "  )\n\n"
                    "Step 3 — Play the scene from the editor:\n"
                    f"  play_scene(scene_path='{scene_path}')\n"
                    "  Confirm with is_playing() → {'playing': true}\n\n"
                    "Step 4 — Inspect the live game:\n"
                    "  get_game_scene_tree() → see the running node hierarchy\n"
                    "  monitor_property(\n"
                    "      node_path='/root/Main/Player',\n"
                    "      property='position',\n"
                    "      samples=30)\n"
                    "  get_property_samples() → collect the sampled values\n"
                    "  find_ui_elements(name_contains='Score') → locate UI controls\n\n"
                    "Step 5 — Simulate input:\n"
                    "  simulate_action(action='ui_right', pressed=true)  # hold\n"
                    "  simulate_action(action='ui_right', pressed=false) # release\n"
                    "  simulate_key(key='Space', pressed=true)\n"
                    "  play_input_sequence(events=[...], delay_ms=100)  # replay macro\n\n"
                    "Step 6 — Assert state:\n"
                    "  assert_node_state(\n"
                    "      node_path='/root/Main/GameManager',\n"
                    "      property='coin_count',\n"
                    "      expected=3,\n"
                    "      op='>='\n"
                    "  )\n\n"
                    "Step 7 — Stop:\n"
                    "  stop_scene()\n\n"
                    "IMPORTANT DISTINCTION:\n"
                    "- play_scene()  → editor play session (live, inspectable, needs probe)\n"
                    "- run_and_capture() → headless subprocess (no editor, no live interaction)"
                ),
            ),
        ]


def _register_script_edit(mcp: FastMCP) -> None:
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
                    "  enable_toolset('scripts')\n\n"
                    "Step 2 — Write the script:\n"
                    f"  write_script(script_path='{script_path}', content='extends Node\n...')\n\n"
                    "Step 3 — Check for parse errors (headless, no editor needed):\n"
                    f"  get_parse_errors(script_path='{script_path}')\n"
                    "  Fix any errors before attaching.\n\n"
                    "Step 4 — Attach to the node:\n"
                    "  enable_toolset('scene_edit')\n"
                    f"  attach_script(node_path='{node_path}', script_path='{script_path}')\n\n"
                    "Step 5 — Iterate with patches (no full rewrite):\n"
                    f"  patch_script(\n"
                    f"      script_path='{script_path}',\n"
                    f"      find='old_code_here',\n"
                    f"      replace='new_code_here'\n"
                    f"  )\n\n"
                    "Step 6 — Verify in-editor (optional):\n"
                    "  get_script_for_node(\n"
                    f"      node_path='{node_path}') → read back the attached script\n"
                    "  get_parse_errors(\n"
                    f"      script_path='{script_path}') → final parse check\n\n"
                    "TIP: Use dry_run=True on any mutating tool to preview before committing."
                ),
            ),
        ]


def _register_debug_scene(mcp: FastMCP) -> None:
    @mcp.prompt(
        name="debug_scene",
        description=(
            "Systematic debugging workflow for a Godot scene or script that is failing. "
            "Uses health_check, get_parse_errors, run_and_capture, and analyze_signal_flow "
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
                    "  enable_toolset('scripts')\n"
                    "  enable_toolset('runtime')\n"
                    "  enable_toolset('analysis')\n"
                    "  enable_toolset('inspection')  [already on by default]\n\n"
                    "PHASE 1 — Quick Health Check\n"
                    "  health_check()\n"
                    "  → Returns server version and bridge connection status.\n"
                    "  get_project_info()\n"
                    "  → Returns project name, Godot version, autoloads, and main scene.\n"
                    "  get_scene_tree(max_depth=2)\n"
                    "  → Spot-check the scene structure for obvious problems.\n\n"
                    "PHASE 2 — Script Analysis (if a script is involved)\n"
                    f"  get_parse_errors(script_path='{script_path or 'res://scripts/my_script.gd'}')"  # noqa: E501
                    "\n  → Fix any parse errors (syntax, missing parentheses, "  # noqa: E501
                    "undefined variables).\n\n"
                    "PHASE 3 — Scene Structure Check\n"
                    "  get_scene_tree(max_depth=-1)\n"
                    "  get_node_properties(node_path='./Player')  "
                    "[or the failing node]\n"
                    "  → Verify nodes exist, scripts are attached, and "
                    "property values are sane.\n\n"
                    "PHASE 4 — Signal Flow Inspection\n"
                    f"  analyze_signal_flow(scene='{scene_path or 'res://scenes/main.tscn'}')"  # noqa: E501
                    "\n  → Look for disconnected signals, wrong method "  # noqa: E501
                    "names, or missing target nodes.\n\n"
                    "PHASE 5 — Headless Run with Logs\n"
                    f"  run_and_capture(scene='{scene_path or ''}', timeout_seconds=5)\n"
                    "  → Read errors[] and warnings[] for runtime failures.\n\n"
                    "PHASE 6 — Live Debug (if the game runs but behaves wrong)\n"
                    "  play_scene(scene_path='...')\n"
                    "  get_game_scene_tree() → verify runtime node hierarchy\n"
                    "  monitor_property(\n"
                    "      node_path='/root/Main/Player',\n"
                    "      property='position',\n"
                    "      samples=30)\n"
                    "  → Check if values change as expected.\n\n"
                    "PHASE 7 — Static Project Analysis\n"
                    "  detect_circular_dependencies() → script A loads B loads A?\n"
                    "  find_unused_resources() → missing textures/sounds that crash on load?\n"
                    "  project_stats() → identify the most complex scenes\n\n"
                    "COMMON FIXES:\n"
                    "- 'Invalid get index' → the node path changed; verify with get_scene_tree().\n"
                    "- 'Method not found' → signal target method was renamed or deleted.\n"
                    "- 'Null instance' → a node was freed (queue_free) but "
                    "something still references it.\n"
                    "- 'Could not load resource' → file path is wrong or the file was deleted.\n"
                    "- 'Parse Error' → fix the line/column reported by get_parse_errors().\n"
                    "- 'Division by zero' → check divisor values with monitor_property().\n\n"
                    "SAFETY: Every mutating tool accepts dry_run=True to preview fixes.\n"
                    "DOCUMENTATION: https://github.com/hybridindie/godot-mcp/blob/main/TUTORIAL.md"
                ),
            ),
        ]


def _register_troubleshoot(mcp: FastMCP) -> None:
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
                    "  health_check()\n"
                    "  → Look at 'bridge.connected' and 'server.version'.\n\n"
                    "STEP 2 — If bridge is disconnected:\n"
                    "  - Godot must be running with the addon enabled.\n"
                    "  - Check Project Settings → Plugins → godot_mcp → Enable.\n"
                    "  - Check the status dock at the bottom of Godot.\n"
                    "  - Verify port 9080 is not blocked by another process.\n"
                    "  - Try health_check() to see the bridge_url the server expects.\n\n"
                    "STEP 3 — If you get 'ToolError: unknown tool':\n"
                    "  - Call list_toolsets() → confirm the toolset is disabled.\n"
                    "  - Call enable_toolset('scene_edit') [or relevant category].\n"
                    "  - Retry the tool call.\n\n"
                    "STEP 4 — If you get PRECONDITION_FAILED:\n"
                    "  - required=active_scene → open/create a .tscn scene first.\n"
                    "  - required=confirm → add confirm=True (or dry_run=True to preview).\n"
                    "  - required=play_session → call play_scene() before live tools.\n"
                    "  - required=runtime_probe → register MCPRuntimeProbe as autoload.\n"
                    "  - required=bridge_connected → see Step 2.\n"
                    "  - required=godot_version → upgrade Godot to 4.4+.\n\n"
                    "STEP 5 — If scripts fail to parse:\n"
                    "  get_parse_errors(script_path='res://scripts/my.gd')\n"
                    "  → Fix reported line/column, then re-run.\n\n"
                    "STEP 6 — If the game crashes on play:\n"
                    "  - run_and_capture(scene='res://scenes/main.tscn', timeout_seconds=5)\n"
                    "  → Check 'errors' and 'warnings' in the result.\n"
                    "  - Look for null references, missing nodes, or "
                    "signal connection failures.\n\n"
                    "STEP 7 — If live input simulation doesn't work:\n"
                    "  - Confirm play_scene() is running (is_playing() → true).\n"
                    "  - Confirm MCPRuntimeProbe is in autoloads (get_project_info()).\n"
                    "  - Check the live scene tree includes the target "
                    "node (get_game_scene_tree()).\n\n"
                    "DOCUMENTATION:\n"
                    "- Tutorial: https://github.com/hybridindie/godot-mcp/blob/main/TUTORIAL.md\n"
                    "- Tool specs: https://github.com/hybridindie/godot-mcp/blob/main/docs/tool-contracts.md\n"
                    "- Architecture: https://github.com/hybridindie/godot-mcp/blob/main/docs/architecture.md"
                ),
            ),
        ]
