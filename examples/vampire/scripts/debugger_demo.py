#!/usr/bin/env python3
"""Interactive demo script for the MCP debugger tools (issue #110).

Connects directly to the Godot addon WebSocket (bypassing the MCP server layer)
to demonstrate the raw debugger protocol commands. In a real MCP client session
this would happen through the MCP server tools instead.

Usage:
    python3 scripts/debugger_demo.py

Requires the Godot editor to be running with the vampire project open and the
MCPRuntimeProbe autoload enabled.
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


async def _enable_toolset(ws, category: str) -> None:
    print(f"\n[1] Enabling '{category}' toolset...")
    resp = await _send(ws, "cmd_enable_toolset", {"category": category})
    print(f"    Result: ok={resp.get('ok')}  result={resp.get('result')}")


async def _play_scene(ws) -> None:
    print("\n[2] Playing the current scene...")
    resp = await _send(ws, "cmd_play_scene", {})
    print(f"    Result: {_pretty(resp.get('result', {}))[:200]}")


async def _set_breakpoint(ws, path: str, line: int) -> None:
    print(f"\n[3] Setting breakpoint at {path}:{line}...")
    resp = await _send(ws, "cmd_set_breakpoint", {"path": path, "line": line})
    print(f"    Result: {_pretty(resp.get('result', {}))}")


async def _force_break(ws) -> None:
    print("\n[4] Forcing a break in the running game...")
    resp = await _send(ws, "cmd_force_break", {})
    print(f"    Result: {_pretty(resp.get('result', {}))}")


async def _get_stack_frames(ws) -> None:
    print("\n[5] Getting stack frames...")
    # First call triggers the request; second call reads the cached reply.
    for attempt in range(1, 4):
        resp = await _send(ws, "cmd_get_stack_frames", {})
        result = resp.get("result", {})
        frames = result.get("frames", [])
        if frames:
            print(f"    Frames count: {len(frames)}")
            for i, frame in enumerate(frames[:5]):
                print(f"      [{i}] {frame.get('func')} @ {frame.get('file')}:{frame.get('line')}")
            return
        print(f"    Attempt {attempt}: cache empty, waiting for async reply...")
        await asyncio.sleep(0.3)
    print("    No frames received (game may not be paused).")


async def _evaluate(ws, expression: str, frame: int = 0) -> None:
    print(f"\n[6] Evaluating expression '{expression}' at frame {frame}...")
    # Poll: first call triggers evaluation; subsequent calls read the cached result.
    for attempt in range(1, 4):
        resp = await _send(
            ws,
            "cmd_evaluate_expression",
            {"expression": expression, "frame": frame},
        )
        result = resp.get("result", {})
        value = result.get("value")
        if value is not None:
            print(f"    Expression: {result.get('expression')}")
            print(f"    Value: {value}")
            return
        print(f"    Attempt {attempt}: result not ready, waiting...")
        await asyncio.sleep(0.3)
    print("    No result (expression may be invalid or game not paused).")


async def _step_into(ws) -> None:
    print("\n[7] Stepping into...")
    resp = await _send(ws, "cmd_step_into", {})
    print(f"    Result: {_pretty(resp.get('result', {}))}")
    # After stepping, wait briefly for the game to hit the next line.
    await asyncio.sleep(0.3)


async def _get_frame_variables(ws, frame: int = 0) -> None:
    print(f"\n[6b] Getting frame variables at frame {frame}...")
    for attempt in range(1, 4):
        resp = await _send(ws, "cmd_get_frame_variables", {"frame": frame})
        result = resp.get("result", {})
        locals_ = result.get("locals", [])
        members = result.get("members", [])
        globals_ = result.get("globals", [])
        if locals_ or members or globals_:
            print(f"    locals:  {len(locals_)}  → {[v.get('name') for v in locals_[:3]]}")
            print(f"    members: {len(members)}  → {[v.get('name') for v in members[:3]]}")
            print(f"    globals: {len(globals_)}  → {[v.get('name') for v in globals_[:3]]}")
            return
        print(f"    Attempt {attempt}: cache empty, waiting for async reply...")
        await asyncio.sleep(0.3)
    print("    No variables received.")


async def _continue(ws) -> None:
    print("\n[8] Continuing execution...")
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

        # Show project info
        info = await _get_project_info(ws)
        print(f"Project: {info.get('name')} (Godot {info.get('godot_version')})")

        # Step 1: Enable debugger toolset
        await _enable_toolset(ws, "debugger")

        # Step 2: Play the scene
        await _play_scene(ws)
        print("\n    ▶ Scene is now running. Wait for it to start, then press Space")
        print("      in the game window (or wait for the auto-tick breakpoint).")
        print("\n    ⚠️  For this demo, we will force a break instead of waiting...")
        await asyncio.sleep(2)

        # Step 3: Force a break
        await _force_break(ws)
        print("    ⏸ Game is paused. Debugger tools are now usable.")
        await asyncio.sleep(1)

        # Step 4: Get stack frames
        await _get_stack_frames(ws)

        # Step 5: Evaluate expressions
        await _evaluate(ws, "GameManager.get_score()", 0)
        await _evaluate(ws, "get_tree().paused", 0)

        # Step 5b: Get frame variables
        await _get_frame_variables(ws, 0)

        # Step 6: Step into
        await _step_into(ws)
        await asyncio.sleep(0.5)
        await _get_stack_frames(ws)

        # Step 7: Continue
        await _continue(ws)
        print("\n    ▶ Game resumed.")

        print("\n" + "=" * 60)
        print("  Demo complete!")
        print("=" * 60)
        print("""
In a real MCP client session (Claude Code / OpenCode), you would call:

  enable_toolset("debugger")
  play_scene("res://scenes/main.tscn")
  force_break()                    # or wait for a set_breakpoint to hit
  get_stack_frames()               # → [{file, line, func}, ...]
  evaluate_expression("health")      # → {expression, value}
  step_into() / step_over()        # → {stepped: true}
  continue_execution()             # → {running: true}

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
