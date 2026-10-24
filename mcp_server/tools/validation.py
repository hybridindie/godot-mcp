"""Project-registered validators, run headless (#758).

The validator runner ships in the addon (`validation_runner.gd`) and runs in the
project, so the same rules apply in the editor and in CI. The server resolves the
project (``GODOT_MCP_PROJECT_DIR`` or the connected editor), finds the addon's
runner (whatever its install path), and parses the one-line JSON result.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastmcp import FastMCP

from mcp_server.agent_errors import AgentToolError
from mcp_server.bridge import Bridge
from mcp_server.categories import ANALYSIS_TAG
from mcp_server.config import ServerConfig
from mcp_server.models.validation import ValidateProjectResult
from mcp_server.runtime import find_godot_binary, resolve_project_dir
from mcp_server.safety import READ_ONLY, PreconditionError, enforce_preconditions

ANALYSIS = {ANALYSIS_TAG}
_MARKER = "GODOT_MCP_VALIDATION "
_TIMEOUT = 120.0


def _find_runner(project_dir: Path) -> str | None:
    """Res:// path of the addon's headless validation runner, whatever the install path."""
    candidates = sorted(project_dir.rglob("addons/godot_mcp/validation_runner.gd"))
    if not candidates:
        return None
    default = project_dir / "addons" / "godot_mcp" / "validation_runner.gd"
    preferred = [p for p in candidates if p == default]
    chosen = (preferred or candidates)[0]
    return "res://" + chosen.relative_to(project_dir).as_posix()


def register_validation(
    mcp: FastMCP, bridge: Bridge, config: ServerConfig
) -> None:
    """Register ``validate_project`` in the analysis toolset."""

    @mcp.tool(meta=READ_ONLY, tags=ANALYSIS)
    @enforce_preconditions
    async def validate_project(include_warnings: bool = False) -> ValidateProjectResult:
        """Run project validators + built-ins (autoloads, deps, unloadable scripts).
        Rules: res://.mcp/validators/*.gd."""
        project_dir = Path(await resolve_project_dir(bridge, config))
        if not project_dir.is_dir():
            raise PreconditionError(
                f"Project directory '{project_dir}' is not accessible from the server.",
                required="project_dir",
            )
        runner = _find_runner(project_dir)
        if runner is None:
            raise PreconditionError(
                "Install the godot-mcp addon in the project to run validators.",
                required="addon_installed",
            )
        binary = find_godot_binary(config)
        if binary is None:
            raise PreconditionError(
                "Godot binary not found. Set GODOT_MCP_GODOT_BIN to your Godot executable.",
                required="godot_bin",
            )
        args = [
            binary,
            "--headless",
            "--path",
            str(project_dir),
            "--script",
            runner,
        ]
        if include_warnings:
            args.extend(["--", "--include-warnings"])
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=_TIMEOUT
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise AgentToolError(
                "TIMEOUT", f"Project validation timed out after {_TIMEOUT:g}s."
            ) from None
        for line in stdout.decode(errors="replace").splitlines():
            if line.startswith(_MARKER):
                try:
                    payload = json.loads(line[len(_MARKER) :])
                except json.JSONDecodeError as exc:
                    raise AgentToolError(
                        "INTERNAL_ERROR", f"Validator result was not JSON: {exc}"
                    ) from exc
                return ValidateProjectResult(
                    **{**payload, "project_dir": str(project_dir)}
                )
        detail = stderr.decode(errors="replace")[-500:].strip()
        raise AgentToolError(
            "INTERNAL_ERROR",
            f"Validator runner produced no result (exit {process.returncode}). {detail}",
        )
