#!/usr/bin/env python3
"""Ollama LLM agent integration for godot-mcp evals.

Connects to a local Ollama instance (default: http://localhost:11434) and uses
qwen3-coder:30b to make tool decisions. The agent receives tool descriptions,
task context, and error hints, then chooses which tool to call next.

Usage:
    python -m evals.ollama_agent --task "Create a Player node and run the game"
    python -m evals.ollama_agent --suite agent_suite_v2
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3-coder:30b"


@dataclass
class LLMCall:
    """A single tool call chosen by the LLM."""

    tool: str
    params: dict[str, Any]
    reasoning: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class LLMStep:
    """One step in an LLM-driven task execution."""

    step: int
    call: LLMCall
    result: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


class OllamaAgent:
    """LLM agent that uses Ollama to choose tools."""

    def __init__(self, bridge: Bridge, model: str = MODEL) -> None:
        self._bridge = bridge
        self._model = model
        self._history: list[dict] = []

    def _system_prompt(self, task: str, available_tools: list[dict]) -> str:
        """Build the system prompt with tool descriptions."""
        tools_desc = "\n".join(
            f"- {t['name']}: {t.get('description', 'No description')[:200]}"
            for t in available_tools
        )
        return (
            f"You are an AI agent controlling a Godot game engine via MCP tools.\n\n"
            f"TASK: {task}\n\n"
            f"AVAILABLE TOOLS:\n{tools_desc}\n\n"
            f"RULES:\n"
            f"1. Only call tools that are listed above.\n"
            f"2. Follow the MANDATORY PROTOCOL: enable_toolset first, then use tools.\n"
            f"3. If a tool fails, read the error hint and choose a recovery action.\n"
            f"4. Respond ONLY with a JSON object:\n"
            f"   {{\"tool\": \"...\", \"params\": {{...}}, \"reasoning\": \"...\"}}\n"
            f"5. Use empty params {{}} if the tool takes no arguments.\n"
            f"6. You MUST take at least one action to make progress on the task.\n"
            f"7. Only return {{\"tool\": \"done\"}} AFTER you have completed the task."
        )

    def _ask(self, task: str, available_tools: list[dict]) -> LLMCall:
        """Ask the LLM to choose the next tool."""
        system = self._system_prompt(task, available_tools)
        # qwen3-coder:30b on Ollama ignores system role; prepend to first user message
        messages = self._history.copy()
        if not messages:
            messages = [{"role": "user", "content": system}]
        else:
            messages.insert(0, {"role": "user", "content": system})

        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": self._model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 500},
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["message"]["content"]

        # Extract token counts from Ollama response
        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)

        # Parse JSON from the response
        try:
            # Sometimes the model wraps JSON in markdown
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            parsed = json.loads(content)
        except (json.JSONDecodeError, IndexError):
            # Fallback: try to extract the first JSON object
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(content[start:end + 1])
                except json.JSONDecodeError:
                    parsed = {
                        "tool": "done",
                        "params": {},
                        "reasoning": f"Parse: {content[:80]}",
                    }
            else:
                parsed = {
                    "tool": "done",
                    "params": {},
                    "reasoning": f"No JSON: {content[:80]}",
                }

        self._history.append({"role": "assistant", "content": json.dumps(parsed)})
        return LLMCall(
            tool=parsed.get("tool", "done"),
            params=parsed.get("params", {}),
            reasoning=parsed.get("reasoning", ""),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def _execute(self, call: LLMCall) -> dict:
        """Execute a tool call via the bridge (async)."""
        if call.tool == "done":
            return {"ok": True, "result": {}, "done": True}

        cmd = f"cmd_{call.tool}"
        try:
            t0 = time.perf_counter()
            response = await self._bridge.send(cmd, call.params)
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            return {
                "ok": response.ok,
                "result": response.result or {},
                "error": response.error,
                "hint": response.hint,
                "done": False,
                "latency_ms": latency_ms,
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "hint": "Bridge execution failed", "done": False}

    def _add_result(self, result: dict) -> None:
        """Add the tool result to history for the LLM."""
        summary = json.dumps({
            "ok": result["ok"],
            "error": result.get("error"),
            "hint": result.get("hint"),
            "result_keys": list(result.get("result", {}).keys()),
        })
        self._history.append({"role": "user", "content": f"Tool result: {summary}"})

    async def run_task(
        self,
        task: str,
        available_tools: list[dict],
        max_steps: int = 10,
    ) -> list[LLMStep]:
        """Run a task with the LLM agent, returning the step-by-step trace."""
        steps: list[LLMStep] = []
        for i in range(max_steps):
            call = self._ask(task, available_tools)
            result = await self._execute(call)
            self._add_result(result)
            steps.append(LLMStep(step=i+1, call=call, result=result))
            if result.get("done") or call.tool == "done":
                break
        return steps


def get_available_tools() -> list[dict]:
    """Return tools that actually exist in the Godot addon bridge."""
    return [
        {
            "name": "get_project_info",
            "description": "Get project name, main scene, autoloads.",
        },
        {
            "name": "get_scene_tree",
            "description": (
                "Get open scene's node hierarchy. Use this to find node paths "
                "before operating on nodes."
            ),
        },
        {
            "name": "create_node",
            "description": (
                "Add a node to the scene. Params: parent_path='.' for root, "
                "node_type (e.g., 'Node2D'), name (node name)."
            ),
        },
        {
            "name": "set_node_property",
            "description": (
                "Set a node property. If the property doesn't exist, the error hint "
                "suggests using get_node_property_list first."
            ),
        },
        {
            "name": "play_scene",
            "description": (
                "Run the game in the editor. Call this BEFORE using any runtime/input tools "
                "that need an active play session."
            ),
        },
        {
            "name": "stop_scene",
            "description": "Stop the running game.",
        },
        {
            "name": "get_game_scene_tree",
            "description": (
                "Get the live game scene tree while game is running. "
                "Use this INSTEAD OF get_scene_tree when the game is playing. "
                "Requires active play session."
            ),
        },
        {
            "name": "simulate_key",
            "description": (
                "Send a key press to the running game. "
                "Requires active play session (call play_scene first)."
            ),
        },
        {
            "name": "get_editor_performance",
            "description": (
                "Read editor FPS and performance. Use when game is NOT running."
            ),
        },
        {
            "name": "write_script",
            "description": (
                "Write a GDScript to a file. "
                "Params: script_path (e.g., res://scripts/foo.gd), content (the script text)."
            ),
        },
        {
            "name": "attach_script",
            "description": (
                "Attach a script to a node. "
                "Params: node_path (the node), script_path (the script file). "
                "The script must already exist."
            ),
        },
        {
            "name": "batch_set_property",
            "description": (
                "Set a property on multiple nodes at once. "
                "More efficient than calling set_node_property for each node individually. "
                "Params: node_paths (array), property, value."
            ),
        },
        {
            "name": "done",
            "description": "Signal that the task is complete. Only call after task is fully done.",
        },
    ]


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Ollama LLM agent for godot-mcp")
    parser.add_argument("--task", default="Create a Node2D named TestNode and run the game")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--max-steps", type=int, default=10)
    args = parser.parse_args()

    bridge = Bridge(BridgeConfig.from_env())
    import asyncio
    asyncio.run(bridge.connect())

    agent = OllamaAgent(bridge, model=args.model)
    tools = get_available_tools()

    async def _run():
        await bridge.connect()
        steps = await agent.run_task(args.task, tools, max_steps=args.max_steps)
        return steps

    steps = asyncio.run(_run())

    print(f"\nTask: {args.task}")
    print("=" * 60)
    for s in steps:
        status = "✅" if s.result.get("ok") else "❌"
        print(f"{status} Step {s.step}: {s.call.tool}({json.dumps(s.call.params)})")
        print(f"   Reasoning: {s.call.reasoning[:80]}")
        if not s.result.get("ok"):
            print(f"   Error: {s.result.get('error')} | {s.result.get('hint')}")
    print("=" * 60)

    bridge.close()


if __name__ == "__main__":
    main()
