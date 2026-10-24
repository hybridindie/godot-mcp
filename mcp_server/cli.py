"""Setup and readiness CLI (#762): ``config`` and ``doctor``.

``config`` prints or merges a client's MCP config without clobbering other
servers. ``doctor`` checks the local install (uv/Python, Godot, the addon, and
the bridge listener) and prints an actionable fix for each failure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import mcp_server
from mcp_server.config import BridgeConfig, ServerConfig
from mcp_server.runtime import find_godot_binary

SERVER_NAME = "godot-mcp"
COMMAND = "uvx"
ARGS = ["godot-editor-mcp"]

# client -> (path template, format, root key)
_CLIENTS: dict[str, tuple[str, str, str]] = {
    "claude-code": ("{project}/.mcp.json", "json", "mcpServers"),
    "cursor": ("{project}/.cursor/mcp.json", "json", "mcpServers"),
    "vscode": ("{project}/.vscode/mcp.json", "json", "servers"),
    "gemini": ("~/.gemini/settings.json", "json", "mcpServers"),
    "codex": ("~/.codex/config.toml", "toml", "mcp_servers"),
    "opencode": ("{project}/opencode.json", "json", "mcp"),
}


def _entry(
    project: Path | None, *, vscode: bool = False, opencode: bool = False
) -> dict[str, Any]:
    if opencode:
        entry: dict[str, Any] = {"type": "local", "command": [COMMAND, *ARGS]}
        if project is not None:
            entry["environment"] = {"GODOT_MCP_PROJECT_DIR": str(project)}
        return entry
    entry = {"command": COMMAND, "args": list(ARGS)}
    if project is not None:
        entry["env"] = {"GODOT_MCP_PROJECT_DIR": str(project)}
    if vscode:
        entry = {"type": "stdio", **entry}
    return entry


def _toml_snippet(project: Path | None) -> str:
    lines = [
        "[mcp_servers.godot-mcp]",
        f'command = "{COMMAND}"',
        'args = ["godot-editor-mcp"]',
    ]
    if project is not None:
        lines.extend(
            [
                "",
                "[mcp_servers.godot-mcp.env]",
                f'GODOT_MCP_PROJECT_DIR = "{project}"',
            ]
        )
    return "\n".join(lines) + "\n"


def _target_path(client: str, project: Path) -> Path:
    template, _kind, _root = _CLIENTS[client]
    return Path(template.format(project=project)).expanduser()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"error: {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"error: {path} must contain a JSON object.")
    return data


def _merge_json(path: Path, root: str, entry: dict[str, Any], *, force: bool) -> dict[str, Any]:
    data = _load_json(path)
    servers = data.setdefault(root, {})
    if not isinstance(servers, dict):
        raise SystemExit(f"error: '{root}' in {path} is not an object.")
    if SERVER_NAME in servers and not force:
        raise SystemExit(
            f"error: {path} already has '{root}.{SERVER_NAME}'; use --force to replace it."
        )
    servers[SERVER_NAME] = entry
    return data


def _strip_toml_table(text: str, header: str) -> str:
    """Remove one TOML table (header until the next table) without touching others."""
    out: list[str] = []
    skipping = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped == f"[{header}]" or stripped.startswith(f"[{header}."):
                skipping = True
                continue
            if skipping:
                skipping = False
        if not skipping:
            out.append(line)
    return "\n".join(out).rstrip() + "\n"


def _config(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve() if args.project else Path.cwd()
    path = _target_path(args.client, project)
    kind = _CLIENTS[args.client][1]
    vscode = args.client == "vscode"

    if kind == "json":
        root = _CLIENTS[args.client][2]
        entry = _entry(
            project if args.project else None,
            vscode=vscode,
            opencode=args.client == "opencode",
        )
        merged = _merge_json(path, root, entry, force=args.force or not args.write)
        text = json.dumps(merged, indent=2) + "\n"
    else:
        snippet = _toml_snippet(project if args.project else None)
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        if existing:
            try:
                tomllib.loads(existing)
            except tomllib.TOMLDecodeError as exc:
                raise SystemExit(f"error: {path} is not valid TOML: {exc}") from exc
            if "[mcp_servers.godot-mcp]" in existing and not args.force:
                raise SystemExit(
                    f"error: {path} already has [mcp_servers.godot-mcp]; use --force to replace it."
                )
            if "[mcp_servers.godot-mcp]" in existing:
                existing = _strip_toml_table(existing, "mcp_servers.godot-mcp")
        text = existing.rstrip() + ("\n\n" if existing.strip() else "") + snippet

    if args.write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")
        return 0
    print(text, end="")
    return 0


def _check(ok: bool, name: str, detail: str, fix: str | None = None) -> bool:
    print(f"[{'ok' if ok else 'fail'}] {name}: {detail}")
    if not ok and fix:
        print(f"        fix: {fix}")
    return ok


def _run_version(binary: list[str]) -> str | None:
    try:
        result = subprocess.run(binary, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    output = (result.stdout or result.stderr).strip()
    return output.splitlines()[0] if output else None


def _find_addon(project: Path) -> Path | None:
    candidates = sorted(project.rglob("addons/godot_mcp/plugin.cfg"))
    if not candidates:
        return None
    default = project / "addons" / "godot_mcp" / "plugin.cfg"
    return next((p for p in candidates if p == default), candidates[0])


def _addon_version(path: Path) -> str | None:
    match = re.search(r'^version="([^"]+)"', path.read_text(encoding="utf-8"), re.M)
    return match.group(1) if match else None


def _addon_enabled(project: Path, plugin: Path) -> bool:
    godot = project / "project.godot"
    if not godot.is_file():
        return False
    rel = "res://" + plugin.relative_to(project).as_posix()
    text = godot.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^enabled=PackedStringArray\((.*?)\)", text, re.M)
    return bool(match and rel in match.group(1))


def _doctor(args: argparse.Namespace) -> int:
    project = Path(
        args.project or os.environ.get("GODOT_MCP_PROJECT_DIR") or Path.cwd()
    ).expanduser().resolve()
    checks: list[bool] = []

    checks.append(
        _check(
            sys.version_info >= (3, 11),
            "python",
            sys.version.split()[0],
            "install Python 3.11+ (uv python install 3.11)",
        )
    )
    uv = shutil.which("uv")
    uv_version = _run_version([uv, "--version"]) if uv else None
    checks.append(
        _check(
            uv is not None and uv_version is not None,
            "uv",
            uv_version or "not found",
            "install uv: https://docs.astral.sh/uv/",
        )
    )
    config = ServerConfig.from_env()
    binary = find_godot_binary(config)
    godot_version = _run_version([binary, "--version"]) if binary else None
    checks.append(
        _check(
            binary is not None and godot_version is not None,
            "godot",
            godot_version or "not found",
            "set GODOT_MCP_GODOT_BIN or put godot on PATH",
        )
    )
    checks.append(
        _check(
            (project / "project.godot").is_file(),
            "project",
            str(project),
            "pass --project <path to a Godot project>",
        )
    )
    plugin = _find_addon(project)
    if plugin is None:
        checks.append(
            _check(
                False,
                "addon",
                "not installed",
                "install the addon: unzip godot_mcp_addon.zip -d <project>",
            )
        )
    else:
        version = _addon_version(plugin)
        checks.append(
            _check(
                version is not None and version == mcp_server.__version__,
                "addon",
                f"{plugin.relative_to(project)} (version {version or 'unknown'}, "
                f"server {mcp_server.__version__})",
                "update the addon and the server to the same release",
            )
        )
        checks.append(
            _check(
                _addon_enabled(project, plugin),
                "addon enabled",
                "enabled in project.godot" if _addon_enabled(project, plugin) else "not enabled",
                "Project Settings → Plugins → enable godot_mcp (or add it to "
                "[editor_plugins] enabled)",
            )
        )
    bridge = BridgeConfig.from_env().url
    parsed = urlparse(bridge)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 9080
    try:
        with socket.create_connection((host, port), timeout=1.5):
            checks.append(
                _check(
                    True,
                    "bridge",
                    f"{host}:{port} reachable (godot_health_check verifies the editor)",
                )
            )
    except OSError:
        checks.append(
            _check(
                False,
                "bridge",
                f"{host}:{port} not reachable",
                "start the server: godot-editor-mcp (then open the project with the addon enabled)",
            )
        )
    return 0 if all(checks) else 1


def config_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="godot-editor-mcp config",
        description="Print or merge a client's MCP config.",
    )
    parser.add_argument("--client", required=True, choices=sorted(_CLIENTS))
    parser.add_argument(
        "--project", default=None, help="Godot project path (project-local clients)"
    )
    parser.add_argument(
        "--write", action="store_true", help="write the merged config"
    )
    parser.add_argument(
        "--force", action="store_true", help="replace an existing godot-mcp entry"
    )
    return parser


def doctor_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="godot-editor-mcp doctor",
        description="Check the local install and print a fix for each failure.",
    )
    parser.add_argument("--project", default=None, help="Godot project path")
    return parser


def main(argv: list[str]) -> int:
    """Dispatch a ``config`` or ``doctor`` subcommand."""
    if not argv or argv[0] not in ("config", "doctor"):
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} {{config,doctor}} ...")
    if argv[0] == "config":
        return _config(config_parser().parse_args(argv[1:]))
    return _doctor(doctor_parser().parse_args(argv[1:]))
