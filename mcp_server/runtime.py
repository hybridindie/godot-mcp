"""Headless runtime loop: run the project and capture its output (issue #13).

The agent's build/verify/fix loop. ``run_and_capture`` launches Godot **headless**
on the project (optionally a specific scene), waits up to a timeout, and returns a
structured summary of errors/warnings/output.

Architectural note: this is the one place the server launches a Godot *process*
directly rather than going through the editor bridge (cf. Article II in
.claude/rules/architecture.md). That is deliberate — running the game for
verification is process execution, not editor control, and Godot exposes no public
GDScript API to read the editor's Output/error log. The bridge remains the only
path for *editor* control; this runner is an isolated, injected concern.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.runtime import LogEntry, RunCaptureResult
from mcp_server.safety import PreconditionError

# Known macOS install location; extend per platform as needed.
_MAC_APP = Path("/Applications/Godot.app/Contents/MacOS/Godot")

_ERROR_RE = re.compile(r"\b(SCRIPT ERROR|ERROR|USER ERROR|Parse Error)\b", re.IGNORECASE)
_WARNING_RE = re.compile(r"\b(WARNING|USER WARNING)\b", re.IGNORECASE)
# A res:// source with a line number, e.g. "res://player.gd:42".
_SOURCE_RE = re.compile(r"(res://\S+?):(\d+)")


async def resolve_project_dir(bridge: Bridge, config: ServerConfig) -> str:
    """Project dir to operate on: explicit config, else the connected editor's project."""
    if config.godot_project_dir:
        return config.godot_project_dir
    response = await bridge.send("cmd_get_project_info")
    project_path = (response.result or {}).get("project_path") if response.ok else None
    if not project_path:
        raise PreconditionError(
            "No project directory. Set GODOT_MCP_PROJECT_DIR, or connect the editor so "
            "the open project can be located.",
            required="project_dir",
        )
    return str(project_path)


def find_godot_binary(config: ServerConfig) -> str | None:
    """Resolve the Godot binary: config → PATH → known app bundle."""
    if config.godot_bin and Path(config.godot_bin).is_file():
        return config.godot_bin
    on_path = shutil.which("godot") or shutil.which("Godot")
    if on_path:
        return on_path
    if _MAC_APP.is_file():
        return str(_MAC_APP)
    return None


@dataclass
class RunOutput:
    """Raw result of a headless run, before summarization."""

    command: list[str]
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    timed_out: bool = False
    duration: float = 0.0


class Runner(Protocol):
    """Runs the project headless. ``binary`` is None when no Godot is available."""

    binary: str | None

    async def run(self, project_dir: str, scene: str | None, timeout: float) -> RunOutput: ...

    async def check_script(
        self, project_dir: str, script_path: str, timeout: float
    ) -> RunOutput: ...

    async def export(
        self, project_dir: str, preset: str, output_path: str, debug: bool, timeout: float
    ) -> RunOutput: ...


@dataclass
class GodotRunner:
    """Launches Godot headless via an asyncio subprocess."""

    config: ServerConfig
    binary: str | None = field(default=None)

    def __post_init__(self) -> None:
        if self.binary is None:
            self.binary = find_godot_binary(self.config)

    async def run(self, project_dir: str, scene: str | None, timeout: float) -> RunOutput:
        command = [self.binary, "--headless", "--path", project_dir]
        if scene:
            command.append(scene)
        return await self._exec(command, timeout)

    async def check_script(self, project_dir: str, script_path: str, timeout: float) -> RunOutput:
        """Parse-check a single script via ``--check-only --script`` (no execution)."""
        command = [
            self.binary,
            "--headless",
            "--path",
            project_dir,
            "--check-only",
            "--script",
            script_path,
        ]
        return await self._exec(command, timeout)

    async def export(
        self, project_dir: str, preset: str, output_path: str, debug: bool, timeout: float
    ) -> RunOutput:
        """Run Godot's export pipeline headlessly for ``preset`` to ``output_path``
        (release unless ``debug``). Requires export templates installed (issue #50).
        """
        flag = "--export-debug" if debug else "--export-release"
        command = [self.binary, "--headless", "--path", project_dir, flag, preset, output_path]
        return await self._exec(command, timeout)

    async def _exec(self, command: list[str | None], timeout: float) -> RunOutput:
        assert self.binary is not None  # callers check availability first
        cmd = [c for c in command if c is not None]
        started = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
        except OSError as exc:
            # e.g. a non-executable binary, or it vanished — surface as a structured
            # error via summarize_run instead of an unstructured exception.
            return RunOutput(
                command=cmd,
                stderr=f"ERROR: failed to launch Godot ({exc}).",
                exit_code=None,
                duration=round(time.monotonic() - started, 3),
            )
        timed_out = False
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except TimeoutError:
            timed_out = True
            proc.kill()
            out, err = await proc.communicate()
        return RunOutput(
            command=cmd,
            stdout=out.decode("utf-8", "replace"),
            stderr=err.decode("utf-8", "replace"),
            exit_code=None if timed_out else proc.returncode,
            timed_out=timed_out,
            duration=round(time.monotonic() - started, 3),
        )


def _classify(line: str) -> LogEntry | None:
    """Classify a single output line as an error/warning LogEntry, or None."""
    kind: str | None = None
    if _ERROR_RE.search(line):
        kind = "error"
    elif _WARNING_RE.search(line):
        kind = "warning"
    if kind is None:
        return None
    source: str | None = None
    line_no: int | None = None
    match = _SOURCE_RE.search(line)
    if match:
        source, line_no = match.group(1), int(match.group(2))
    return LogEntry(type=kind, message=line.strip(), source=source, line=line_no)


def summarize_run(output: RunOutput) -> RunCaptureResult:
    """Parse a RunOutput's combined stdout/stderr into a structured summary."""
    errors: list[LogEntry] = []
    warnings: list[LogEntry] = []
    plain: list[str] = []
    for raw in (output.stdout + "\n" + output.stderr).splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        entry = _classify(line)
        if entry is None:
            plain.append(line)
        elif entry.type == "error":
            errors.append(entry)
        else:
            warnings.append(entry)
    return RunCaptureResult(
        ran=True,
        exit_code=output.exit_code,
        timed_out=output.timed_out,
        duration_seconds=output.duration,
        errors=errors,
        warnings=warnings,
        output=plain,
        command=output.command,
    )
