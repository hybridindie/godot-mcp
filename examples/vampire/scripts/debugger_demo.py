#!/usr/bin/env python3
"""Interactive demo script for the MCP debugger tools (issue #110).

Connects directly to the Godot addon WebSocket (bypassing the MCP server layer)
to demonstrate the raw debugger protocol commands. In a real MCP client session
this would happen through the MCP server tools instead; toolset gating
(``enable_toolset``) is a *server-side* concern, so this direct-to-addon demo
skips it.

Usage:
    python3 scripts/debugger_demo.py

Requires the Godot editor to be running with the vampire project open and the
MCPRuntimeProbe autoload enabled.

Note (issue #677): the paused-frame call stack (``cmd_get_stack_frames``) and
frame variables (``cmd_get_frame_variables``) are UNSUPPORTED on Godot 4.7 — the
engine serves them to its own debugger, not to plugins. Expression evaluation
(``cmd_evaluate_expression``) runs *in the running game* via the probe's
``Expression`` path (global scope, not frame-scoped), so it works whether or not
the game is paused.
"""

from __future__ import annotations

import asyncio
import json

import websockets

BRIDGE_URL = "ws://localhost:9080"


def _pretty(data: dict) -> str:
    return json.dumps(data, indent=2)


async def _send(ws, cmd: str, params: dict | None = None) -> dict:
    envelope = {"id": f"demo-{cmd}", "command": cmd, "params": params or {}}
    await ws.send(json.dumps(envelope))
    raw = await asyncio.wait_for(ws.recv(), timeout=5)
    return json.loads(raw)


async def _play_scene(ws) -> None:
    print("\n[1] Playing the current scene...")
    resp = await _send(ws, "cmd_play_scene", {})
    print(f"    Result: {_pretty(resp.get('result', {}))[:200]}")


async def _set_breakpoint(ws, path: str, line: int) -> None:
    print(f"\n[2] Setting breakpoint at {path}:{line}...")
    resp = await _send(ws, "cmd_set_breakpoint", {"path": path, "line": line})
    print(f"    Result: {_pretty(resp.get('result', {}))}")


async def _force_break(ws) -> None:
    print("\n[3] Forcing a break in the running game...")
    resp = await _send(ws, "cmd_force_break", {})
    print(f"    Result: {_pretty(resp.get('result', {}))}")


async def _evaluate(ws, expression: str) -> None:
    print(f"\n[4] Evaluating expression '{expression}' (in-game, global scope)...")
    # Poll: the first call dispatches the in-game evaluation; subsequent calls read
    # the reply (it is request-scoped server-side, but the raw addon command uses a
    # stable "" id here).
    for attempt in range(1, 4):
        resp = await _send(ws, "cmd_evaluate_expression", {"expression": expression})
        result = resp.get("result", {})
        if result.get("ready") and result.get("evaluated"):
            print(f"    Expression: {result.get('expression')}")
            print(f"    Value: {result.get('value')}  error={result.get('error', '')!r}")
            return
        print(f"    Attempt {attempt}: result not ready, waiting...")
        await asyncio.sleep(0.3)
    print("    No result (expression may be invalid).")


async def _step_into(ws) -> None:
    print("\n[5] Stepping into (requires the game to be paused)...")
    resp = await _send(ws, "cmd_step_into", {})
    print(f"    Result: {_pretty(resp.get('result', {}))}")
    await asyncio.sleep(0.3)


async def _continue(ws) -> None:
    print("\n[6] Continuing execution...")
    resp = await _send(ws, "cmd_continue_execution", {})
    print(f"    Result: {_pretty(resp.get('result', {}))}")


async def _get_project_info(ws) -> dict:
    resp = await _send(ws, "cmd_get_project_info", {})
    return resp.get("result", {})


async def _demo() -> None:
    print("=" * 60)
    print("  godot-mcp Debugger Tool Demo")
    print("=" * 60)
    print(f"Connecting to addon at {BRIDGE_URL}...")

    async with websockets.connect(BRIDGE_URL) as ws:
        # Warm-up: confirm connection
        ping = await _send(ws, "cmd_ping", {})
        if not ping.get("ok"):
            print("Failed to connect. Is Godot running with the addon enabled?")
            return
        print("Connected ✅")

        info = await _get_project_info(ws)
        print(f"Project: {info.get('name')} (Godot {info.get('godot_version')})")

        # Play the scene, then force a break so stepping is usable.
        await _play_scene(ws)
        print("\n    ▶ Scene is now running.")
        await asyncio.sleep(2)
        await _force_break(ws)
        print("    ⏸ Game is paused. Stepping tools are now usable.")
        await asyncio.sleep(1)

        # Expression evaluation runs in the game (not at a paused frame).
        await _evaluate(ws, "GameManager.get_score()")
        await _evaluate(ws, "get_tree().paused")

        await _step_into(ws)
        await _continue(ws)
        print("\n    ▶ Game resumed.")

        print("\n" + "=" * 60)
        print("  Demo complete!")
        print("=" * 60)
        print("""
In a real MCP client session (Claude Code / OpenCode), you would call the
server tools (enable the `debugger` toolset first):

  godot_enable_toolset("debugger")
  godot_runtime_play_scene()
  godot_debugger_force_break()             # or wait for a set_breakpoint to hit
  godot_debugger_evaluate_expression("GameManager.get_score()")
                                           # → {expression, value, evaluated, error}
  godot_debugger_step_into()               # → {stepped: true}
  godot_debugger_continue_execution()      # → {running: true}

On Godot 4.7 the paused-frame stack/variable tools
(`godot_debugger_get_stack_frames`, `godot_debugger_get_frame_variables`) are
UNSUPPORTED (#677) — evaluate named values with `evaluate_expression` instead.

The example project's DebuggerDemo node has a built-in breakpoint
at line 43 (on Space / click input) for hands-on experimentation.
""")


if __name__ == "__main__":
    try:
        asyncio.run(_demo())
    except KeyboardInterrupt:
        print("\nDemo cancelled.")
    except Exception as e:
        print(f"\nError: {e}")
        print("Make sure Godot is running with the vampire project and the MCP addon is enabled.")
