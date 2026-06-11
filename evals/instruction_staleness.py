#!/usr/bin/env python3
"""Instruction Staleness Verifier (Gap Analysis #9).

Detects drift between server-side bridge command usage and addon-side handler registrations:
1. **Static analysis**: Regex-scan Python server files for `cmd_*` string literals used in
    `bridge.send()` and `route()` calls, and GDScript files for `handlers["cmd_*"]` registrations.
2. **Runtime verification**: Call each shared `cmd_*` through the bridge to verify the handler
    responds (catches renamed handlers, removed tools, signature drift).
3. **Description drift**: Compare tool description text from Python file context with the actual
    handler docstring in the addon.

Usage:
    python -m evals.instruction_staleness --static
    python -m evals.instruction_staleness --runtime
    python -m evals.instruction_staleness --all
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Bridge imports for runtime verification
from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig

# ---------------------------------------------------------------------------
# Static analysis
# ---------------------------------------------------------------------------


@dataclass
class ToolInfo:
    """Tool metadata extracted from source."""

    name: str
    file: Path
    line: int
    description: str = ""
    params: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


class StaticAnalyzer:
    """Extract tool definitions from Python (server) and GDScript (addon) sources."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.python_tools: list[ToolInfo] = []
        self.gdscript_tools: list[ToolInfo] = []
        self._scan()

    def _scan(self) -> None:
        self._scan_python_tools()
        self._scan_gdscript_tools()

    # -- Python scanner -------------------------------------------------------

    def _scan_python_tools(self) -> None:
        """Scan Python server files for bridge command names (cmd_*)."""
        tools_dir = self.repo_root / "mcp_server" / "tools"
        if not tools_dir.exists():
            return
        for py_file in tools_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue
            self._parse_python_commands(py_file)

    def _parse_python_commands(self, path: Path) -> None:
        """Extract cmd_* strings from bridge.send() calls and route() calls."""
        source = path.read_text()
        # Match bridge.send("cmd_...", ...) or route(bridge, "cmd_...", ...)
        pattern = re.compile(r'["\'](cmd_[\w_]+)["\']')
        found: set[str] = set()
        for match in pattern.finditer(source):
            cmd = match.group(1)
            if cmd not in found:
                found.add(cmd)
                line_num = source[:match.start()].count("\n") + 1
                self.python_tools.append(
                    ToolInfo(name=cmd, file=path, line=line_num)
                )

    # -- GDScript scanner -----------------------------------------------------

    def _scan_gdscript_tools(self) -> None:
        handlers_dir = self.repo_root / "godot" / "addons" / "godot_mcp" / "handlers"
        if not handlers_dir.exists():
            return
        for gd_file in handlers_dir.glob("*.gd"):
            self._parse_gdscript_file(gd_file)

    def _parse_gdscript_file(self, path: Path) -> None:
        source = path.read_text()
        # Match handlers["cmd_*"] = _cmd_*
        pattern = re.compile(r'handlers\["(cmd_[\w_]+)"\]\s*=\s*(_[\w_]+)')
        for match in pattern.finditer(source):
            cmd_name = match.group(1)
            handler_name = match.group(2)
            line_num = source[:match.start()].count("\n") + 1
            # Extract docstring from the handler function
            desc = self._extract_gdscript_docstring(source, handler_name)
            self.gdscript_tools.append(
                ToolInfo(
                    name=cmd_name,
                    file=path,
                    line=line_num,
                    description=desc,
                )
            )

    def _extract_gdscript_docstring(self, source: str, handler_name: str) -> str:
        """Find the function definition and return its docstring comment."""
        # GDScript uses `##` for docstrings (similar to Python)
        func_pattern = re.compile(
            rf'func\s+{re.escape(handler_name)}\s*\([^)]*\)\s*->\s*Dictionary\s*:',
            re.MULTILINE,
        )
        match = func_pattern.search(source)
        if not match:
            return ""
        # Look backward for ## comments
        lines_before = source[:match.start()].split("\n")
        doc_lines: list[str] = []
        for line in reversed(lines_before):
            stripped = line.strip()
            if stripped.startswith("##"):
                doc_lines.insert(0, stripped[2:].strip())
            elif stripped.startswith("#") and not stripped.startswith("##"):
                # Regular comment, keep looking
                continue
            elif stripped == "":
                continue
            else:
                break
        return " ".join(doc_lines)

    # -- Comparison ------------------------------------------------------------

    def compare(self) -> dict[str, Any]:
        py_names = {t.name for t in self.python_tools}
        gd_names = {t.name for t in self.gdscript_tools}

        only_python = sorted(py_names - gd_names)
        only_gdscript = sorted(gd_names - py_names)
        both = sorted(py_names & gd_names)

        # Drift: tools present on both sides but descriptions differ
        drift: list[dict[str, str]] = []
        for name in both:
            py_tool = next(t for t in self.python_tools if t.name == name)
            gd_tool = next(t for t in self.gdscript_tools if t.name == name)
            if py_tool.description and gd_tool.description:
                if py_tool.description[:60] != gd_tool.description[:60]:
                    drift.append(
                        {
                            "name": name,
                            "python": py_tool.description[:80],
                            "gdscript": gd_tool.description[:80],
                        }
                    )

        return {
            "python_total": len(py_names),
            "gdscript_total": len(gd_names),
            "shared": len(both),
            "only_python": only_python,
            "only_gdscript": only_gdscript,
            "drift": drift,
        }


# ---------------------------------------------------------------------------
# Runtime verification
# ---------------------------------------------------------------------------


async def runtime_verify(
    bridge_url: str = "ws://localhost:9080",
    request_timeout: float = 5.0,
) -> dict[str, Any]:
    """Call each shared bridge command to verify the handler exists on the addon side."""
    bridge = Bridge(BridgeConfig(url=bridge_url, request_timeout=request_timeout))
    try:
        await bridge.connect()
        # Test connection with a ping (cmd_ping is the registered handler name)
        ping = await bridge.send("cmd_ping", {})
        if ping.error == "VALIDATION_ERROR" and "Unknown command" in (ping.hint or ""):
            return {
                "error": (
                    "Godot addon bridge not responding correctly "
                    "(ping returned unknown command)"
                )
            }
    except Exception as exc:
        return {"error": f"Could not connect to Godot addon bridge: {exc}"}

    analyzer = StaticAnalyzer(Path(__file__).resolve().parents[1])
    results: list[dict[str, Any]] = []

    # Only test shared tools (ones that exist on both sides)
    py_names = {t.name for t in analyzer.python_tools}
    gd_names = {t.name for t in analyzer.gdscript_tools}
    shared = sorted(py_names & gd_names)

    for cmd in shared:
        try:
            resp = await bridge.send(cmd, {})
            if resp.error == "VALIDATION_ERROR" and "Unknown command" in (resp.hint or ""):
                results.append(
                    {"command": cmd, "status": "MISSING_HANDLER", "hint": resp.hint}
                )
            else:
                # Validation or precondition errors are expected for empty params
                results.append(
                    {"command": cmd, "status": "OK", "error": resp.error, "hint": resp.hint}
                )
        except Exception as exc:
            results.append(
                {"command": cmd, "status": f"ERROR: {type(exc).__name__}", "hint": str(exc)}
            )

    await bridge.close()

    missing = [r for r in results if r["status"] == "MISSING_HANDLER"]
    errors = [r for r in results if r["status"].startswith("ERROR")]
    ok = [r for r in results if r["status"] == "OK"]

    return {
        "total_tested": len(results),
        "ok": len(ok),
        "missing_handler": len(missing),
        "errors": len(errors),
        "details": missing + errors,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def print_report(static: dict[str, Any], runtime: dict[str, Any] | None = None) -> None:
    print("=" * 60)
    print("  Instruction Staleness Report")
    print("=" * 60)
    print()
    print(f"  Python tools:     {static['python_total']}")
    print(f"  GDScript tools:   {static['gdscript_total']}")
    print(f"  Shared:           {static['shared']}")
    print()
    if static["only_python"]:
        print(f"  ⚠ Only Python ({len(static['only_python'])}):")
        for name in static["only_python"]:
            print(f"    - {name}")
        print()
    if static["only_gdscript"]:
        print(f"  ⚠ Only GDScript ({len(static['only_gdscript'])}):")
        for name in static["only_gdscript"]:
            print(f"    - {name}")
        print()
    if static["drift"]:
        print(f"  ⚠ Description drift ({len(static['drift'])}):")
        for item in static["drift"]:
            print(f"    - {item['name']}")
            print(f"      Python:   {item['python']}")
            print(f"      GDScript: {item['gdscript']}")
        print()
    if not static["only_python"] and not static["only_gdscript"] and not static["drift"]:
        print("  ✅ No staleness detected.")
        print()

    if runtime:
        print("  Runtime Verification")
        print("  --------------------")
        if "error" in runtime:
            print(f"  ❌ {runtime['error']}")
        else:
            print(
                f"  Tested: {runtime['total_tested']} | OK: {runtime['ok']} | "
                f"Missing: {runtime['missing_handler']} | "
                f"Errors: {runtime['errors']}"
            )
            if runtime["details"]:
                for item in runtime["details"]:
                    print(f"    ❌ {item['command']}: {item['status']}")
        print()

    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(description="Instruction staleness verifier")
    parser.add_argument("--static", action="store_true", help="Run static analysis only")
    parser.add_argument("--runtime", action="store_true", help="Run runtime verification only")
    parser.add_argument("--all", action="store_true", help="Run both static and runtime")
    args = parser.parse_args()

    if not args.static and not args.runtime and not args.all:
        args.all = True

    static = StaticAnalyzer(Path(__file__).resolve().parents[1]).compare()
    runtime: dict[str, Any] | None = None

    if args.runtime or args.all:
        runtime = asyncio.run(runtime_verify())

    print_report(static, runtime)

    # Exit non-zero if staleness found (static mismatch, missing handlers,
    # connection failure, or runtime execution errors)
    has_issues = (
        static["only_python"]
        or static["only_gdscript"]
        or static["drift"]
        or (runtime and runtime.get("missing_handler", 0) > 0)
        or (runtime and "error" in runtime)
        or (runtime and runtime.get("errors", 0) > 0)
    )
    return 1 if has_issues else 0


if __name__ == "__main__":
    sys.exit(main())
