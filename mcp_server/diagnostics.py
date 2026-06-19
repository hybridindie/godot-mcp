"""Diagnostics and capability-discovery tool.

Provides a single ``get_server_info`` call that returns everything the client
needs to understand the server's surface: toolsets, tool counts per category,
prompts, resources, bridge state, Godot version, and common troubleshooting
scenarios. Designed so an LLM can call it once at session start and build a
complete mental model.
"""

from __future__ import annotations

from fastmcp import FastMCP
from pydantic import BaseModel

from mcp_server import CONTRACT_VERSION, MIN_COMPATIBLE_CONTRACT, __version__
from mcp_server.bridge import Bridge
from mcp_server.categories import CORE_TAG
from mcp_server.config import ServerConfig
from mcp_server.safety import READ_ONLY
from mcp_server.toolsets import ToolsetManager


class ToolsetSummary(BaseModel):
    """Summary of one toolset for the diagnostics report."""

    name: str
    enabled: bool
    description: str
    tool_count: int
    min_godot: str | None = None


class BridgeDiagnostics(BaseModel):
    """Bridge and editor state snapshot."""

    connected: bool
    url: str
    godot_version: str | None = None
    project_name: str | None = None
    project_path: str | None = None


class ServerDiagnostics(BaseModel):
    """Complete server capability and health snapshot.

    This is the authoritative response to ``get_server_info`` — it tells the
    client everything about what is available, what is enabled, and how to fix
    common problems.
    """

    server: str
    version: str
    # Contract/compat negotiation surface (#196), distinct from the CalVer
    # `version`. A client is compatible when
    # ``min_compatible_contract <= client_contract <= contract_version``.
    contract_version: int
    min_compatible_contract: int
    transport: str
    toolsets: list[ToolsetSummary]
    prompts: list[str]
    resources: list[str]
    bridge: BridgeDiagnostics
    active_scene: str | None = None
    common_errors: list[dict[str, str]]
    next_steps: list[str]


def _count_tools_by_tag(mcp: FastMCP, tag: str) -> int:
    """Count registered tools carrying a given category tag."""
    count = 0
    # Tools are stored in the local provider's _components dict under 'tool:{name}@' keys.
    components = getattr(getattr(mcp, "_local_provider", None), "_components", {})
    for key, component in components.items():
        if not key.startswith("tool:"):
            continue
        if tag in (getattr(component, "tags", set())):
            count += 1
    return count


def _list_prompts(mcp: FastMCP) -> list[str]:
    """Return names of all registered prompts."""
    names: list[str] = []
    components = getattr(getattr(mcp, "_local_provider", None), "_components", {})
    for key, component in components.items():
        if not key.startswith("prompt:"):
            continue
        name = getattr(component, "name", "")
        if name:
            names.append(name)
    return names


def _list_resources(mcp: FastMCP) -> list[str]:
    """Return URIs of all registered resources."""
    uris: list[str] = []
    components = getattr(getattr(mcp, "_local_provider", None), "_components", {})
    for key, component in components.items():
        if not key.startswith("resource:"):
            continue
        uri = getattr(component, "uri", "")
        if uri:
            uris.append(str(uri))
    return uris


async def _fetch_bridge_diagnostics(bridge: Bridge) -> BridgeDiagnostics:
    """Snapshot the bridge state and, if connected, query Godot for version/project."""
    url = getattr(bridge, "_config", None)
    url_str = str(url.url) if url else "ws://localhost:9080"
    if not bridge.connected:
        return BridgeDiagnostics(
            connected=False,
            url=url_str,
            godot_version=None,
            project_name=None,
            project_path=None,
        )
    response = await bridge.send("cmd_get_project_info", timeout=3.0)
    if response.ok and response.result:
        result = response.result
        return BridgeDiagnostics(
            connected=True,
            url=url_str,
            godot_version=result.get("godot_version"),
            project_name=result.get("name"),
            project_path=result.get("project_path"),
        )
    return BridgeDiagnostics(
        connected=True,
        url=url_str,
        godot_version=None,
        project_name=None,
        project_path=None,
    )


async def _fetch_active_scene(bridge: Bridge) -> str | None:
    """Return the currently open scene path, or None."""
    if not bridge.connected:
        return None
    response = await bridge.send("cmd_get_active_scene", timeout=3.0)
    if response.ok and response.result:
        result = response.result
        if result.get("is_open"):
            return result.get("path")
    return None


COMMON_ERRORS: list[dict[str, str]] = [
    {
        "symptom": "ToolError: unknown tool",
        "cause": "The toolset containing that tool is not enabled.",
        "fix": "Call enable_toolset(\"scene_edit\") "
        "or the relevant category before using the tool.",
    },
    {
        "symptom": "BRIDGE_DISCONNECTED",
        "cause": "Godot is not running or the addon is not enabled.",
        "fix": "Open Godot with the project and enable the addon in Project Settings.",
    },
    {
        "symptom": "PRECONDITION_FAILED: required=active_scene",
        "cause": "No .tscn scene is open in the editor.",
        "fix": "Open a scene file in Godot, or call create_scene() to make one.",
    },
    {
        "symptom": "PRECONDITION_FAILED: required=confirm",
        "cause": "Destructive tool (delete_node, reload_scene) needs explicit confirmation.",
        "fix": "Add confirm=True to the call, or use dry_run=True to preview first.",
    },
    {
        "symptom": "PRECONDITION_FAILED: required=play_session",
        "cause": "Live runtime/input tools need an active editor play session.",
        "fix": "Call play_scene() first, and ensure the runtime probe autoload is registered.",
    },
    {
        "symptom": "PRECONDITION_FAILED: required=runtime_probe",
        "cause": "The game was launched from the editor but lacks the MCPRuntimeProbe autoload.",
        "fix": "Register MCPRuntimeProbe as an autoload in Project Settings.",
    },
    {
        "symptom": "PRECONDITION_FAILED: required=godot_version",
        "cause": "The connected Godot editor is older than the toolset's minimum.",
        "fix": "Upgrade to Godot 4.4 or newer.",
    },
    {
        "symptom": "RESOURCE_NOT_FOUND",
        "cause": "A node, scene, script, or resource path does not exist.",
        "fix": "Verify the path with get_scene_tree() or get_filesystem_tree() first.",
    },
]


def _build_toolset_summaries(mcp: FastMCP, manager: ToolsetManager) -> list[ToolsetSummary]:
    """Build summaries with live tool counts for every known toolset."""
    summaries: list[ToolsetSummary] = []
    for info in manager.status():
        summaries.append(
            ToolsetSummary(
                name=info.name,
                enabled=info.enabled,
                description=info.description,
                tool_count=_count_tools_by_tag(mcp, info.name),
                min_godot=info.min_godot,
            )
        )
    return summaries


def _next_steps(bridge_connected: bool, active_scene: str | None) -> list[str]:
    """Suggest what the agent should do based on current state."""
    steps: list[str] = []
    if not bridge_connected:
        steps.append(
            "BRIDGE IS OFFLINE: Open Godot with the addon enabled, then retry. "
            "The addon lives at godot/addons/godot_mcp/."
        )
        return steps
    steps.append(
        "Bridge is online. Call list_toolsets() then enable_toolset(...) "
        "for the work you plan to do."
    )
    if active_scene is None:
        steps.append("No scene is open. Open or create a scene before editing nodes.")
    else:
        steps.append(f"Active scene: {active_scene}. Ready for scene editing.")
    steps.append(
        "For live testing, register MCPRuntimeProbe as an autoload, "
        "then play_scene()."
    )
    return steps


# -- registration -----------------------------------------------------------

def register_diagnostics(
    mcp: FastMCP,
    bridge: Bridge,
    config: ServerConfig,
    manager: ToolsetManager,
) -> None:
    """Register the get_server_info diagnostics tool."""

    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    async def get_server_info() -> ServerDiagnostics:
        """Return a comprehensive snapshot of the server's capabilities, toolsets,
        prompts, bridge state, and common troubleshooting scenarios.

        Use this at the **start of every session** to orient the agent:
        it tells you which toolsets are available, how many tools each has,
        whether Godot is connected, what scene is open, and what to do next.
        """
        bridge_diag = await _fetch_bridge_diagnostics(bridge)
        active_scene = await _fetch_active_scene(bridge)
        return ServerDiagnostics(
            server="godot-mcp",
            version=__version__,
            contract_version=CONTRACT_VERSION,
            min_compatible_contract=MIN_COMPATIBLE_CONTRACT,
            transport=config.transport,
            toolsets=_build_toolset_summaries(mcp, manager),
            prompts=_list_prompts(mcp),
            resources=_list_resources(mcp),
            bridge=bridge_diag,
            active_scene=active_scene,
            common_errors=COMMON_ERRORS,
            next_steps=_next_steps(bridge_diag.connected, active_scene),
        )
