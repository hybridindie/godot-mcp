#!/usr/bin/env python3
"""Expanded real LLM agent evaluation for godot-mcp — comprehensive tool coverage.

Tests 30+ tasks covering all available bridge tools, including:
- Inspection, mutation, script management
- Scene sessions, runtime, batch operations
- End-to-end multi-tool workflows
- Physics, profiling, signal connections

Usage:
    python -m evals.llm_eval_v2
    python -m evals.llm_eval_v2 --tasks inspect_scene_tree script_write_and_read
    python -m evals.llm_eval_v2 --max-steps 12 --variant post-pr-v2
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from evals.agent_suite_v2 import (
    BridgeConnector,
    TaskScore,
)
from evals.mlflow_tracker import EvalTracker
from evals.ollama_agent import OllamaAgent
from evals.profiler import ToolProfiler

# ---------------------------------------------------------------------------
# Token tracking
# ---------------------------------------------------------------------------


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------


class ErrorTaxonomy:
    """Categorize errors into agent vs precondition vs infrastructure vs bug."""

    AGENT_PATTERNS = [
        "unknown tool",
        "unknown command",
        "has no property",
        "invalid parameter",
        "missing required",
    ]
    PRECONDITION_PATTERNS = [
        "no play session",
        "not found",
        "no node",
        "toolset not enabled",
        "requires",
        "confirm",
    ]
    INFRA_PATTERNS = [
        "bridge",
        "disconnected",
        "timeout",
        "not running",
        "connection",
    ]

    @classmethod
    def classify(cls, error: str, hint: str) -> str:
        text = f"{error} {hint}".lower()
        for p in cls.INFRA_PATTERNS:
            if p in text:
                return "infrastructure"
        for p in cls.PRECONDITION_PATTERNS:
            if p in text:
                return "precondition"
        for p in cls.AGENT_PATTERNS:
            if p in text:
                return "agent"
        return "unknown"


# ---------------------------------------------------------------------------
# Git SHA for regression tracking
# ---------------------------------------------------------------------------


def get_git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        return result.stdout.strip()[:8] if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# All available tools for the LLM agent
# ---------------------------------------------------------------------------


def get_available_tools() -> list[dict]:
    """Return ALL tools available through the Godot addon bridge."""
    return [
        {"name": "ping", "description": "Check connection health."},
        {"name": "get_project_info", "description": "Get project info."},
        {"name": "get_scene_tree", "description": "Get scene hierarchy."},
        {"name": "get_node_properties", "description": "Get node properties."},
        {"name": "get_node_property_list", "description": "Get property names."},
        {"name": "create_node", "description": "Add node. Params: parent_path, node_type, name."},
        {
            "name": "set_node_property",
            "description": "Set property. Params: node_path, property, value.",
        },
        {"name": "delete_node", "description": "Delete node. Needs confirm=true."},
        {"name": "rename_node", "description": "Rename node. Params: node_path, new_name."},
        {"name": "save_scene", "description": "Save open scene."},
        {"name": "attach_script", "description": "Attach script. Params: node_path, script_path."},
        {
            "name": "connect_signal",
            "description": (
                "Connect a signal from one node to another node's method. "
                "Example: connect_signal with source_path='Player', "
                "signal_name='ready', target_path='Background', "
                "method_name='_ready'."
            ),
        },
        {"name": "write_script", "description": "Write script. Params: script_path, content."},
        {"name": "read_script", "description": "Read script. Params: script_path."},
        {"name": "list_scripts", "description": "List all scripts."},
        {
            "name": "patch_script",
            "description": "Patch script. Params: script_path, find, replace.",
        },
        {"name": "get_script_for_node", "description": "Get node's script. Params: node_path."},
        {"name": "list_open_scenes", "description": "List open scenes."},
        {"name": "open_scene", "description": "Open scene. Params: scene_path."},
        {"name": "save_all_scenes", "description": "Save all scenes."},
        {"name": "select_nodes", "description": "Select nodes. Params: node_paths."},
        {"name": "play_scene", "description": "Run game. Call before runtime tools."},
        {"name": "stop_scene", "description": "Stop game."},
        {"name": "get_game_scene_tree", "description": "Get live tree. Needs play session."},
        {"name": "simulate_key", "description": "Simulate key. Needs play session."},
        {
            "name": "batch_set_property",
            "description": "Batch set property. Params: node_paths, property, value.",
        },
        {"name": "find_nodes_by_type", "description": "Find by type. Params: parent_path, type."},
        {
            "name": "setup_physics_body",
            "description": "Setup physics. Params: node_path, properties.",
        },
        {"name": "get_editor_performance", "description": "Get editor FPS."},
        {"name": "get_performance_monitors", "description": "Get monitors. Needs play session."},
        {"name": "get_stack_frames", "description": "Get stack. Needs play session."},
        {"name": "evaluate_expression", "description": "Eval expression. Needs play session."},
        {"name": "done", "description": "Task done. Call last."},
    ]


# ---------------------------------------------------------------------------
# Task prompts — expanded coverage
# ---------------------------------------------------------------------------

TASK_PROMPTS: dict[str, str] = {
    # === INSPECTION (4 tasks) ===
    "inspect_scene_tree": (
        "Get the full scene tree and find all Sprite2D nodes. Report how many Sprite2D nodes exist."
    ),
    "inspect_node_properties": (
        "Get the properties of the Background node. "
        "Call get_node_properties with node_path='Background'. "
        "Report its position."
    ),
    "inspect_property_list": (
        "Get all valid properties for the Player node using get_node_property_list, "
        "then set its position to (200, 200) using set_node_property."
    ),
    "inspect_find_by_type": (
        "Call find_nodes_by_type to find all nodes of type CollisionShape2D. "
        "Report the full paths found."
    ),
    # === MUTATION (5 tasks) ===
    "mutate_create_and_property": (
        "Create a Node2D named 'MutTest' and set its position to (50, 50)."
    ),
    "mutate_delete_with_confirm": (
        "Create a Node2D named 'MutTest', then delete it. You MUST confirm the deletion."
    ),
    "mutate_rename": (
        "Create a Node2D named 'RenameMe', then rename it to 'RenamedNode'."
    ),
    "mutate_save_scene": ("Save the current scene."),
    "mutate_attach_script": (
        "Attach the script at res://scripts/debugger_demo.gd to the Background node. "
        "Step 1: Call get_script_for_node with node_path='Background' to verify it has no script. "
        "Step 2: Call attach_script with node_path='Background' and script_path='res://scripts/debugger_demo.gd'. "
        "Step 3: Call get_script_for_node again to confirm."
    ),
    # === SCRIPTS (4 tasks) ===
    "script_write_and_read": (
        "Write a GDScript to res://scripts/eval_test_v2.gd that extends Node "
        "and prints 'hello world'. Then read it back to verify."
    ),
    "script_patch": (
        "Patch res://scripts/eval_test_v2.gd to replace 'hello world' with 'patched'. "
        "Then read the file to confirm the patch."
    ),
    "script_list": ("List all scripts in the project. Report the count."),
    "script_get_for_node": (
        "Get the script attached to the Background node. "
        "Call get_script_for_node with node_path='Background'. "
        "If the node has no script attached, the result will show script_path=null."
    ),
    # === SCENE SESSION (3 tasks) ===
    "scene_list_and_open": ("List all open scenes, then save all open scenes."),
    "scene_select_nodes": ("Select the Player node in the editor."),
    # === SIGNALS (2 tasks) ===
    "signal_connect_ready": (
        "Connect the Player node's 'ready' signal to the Background node's '_ready' method. "
        "Call connect_signal with: source_path='Player', signal_name='ready', "
        "target_path='Background', method_name='_ready'."
    ),
    # === RUNTIME (4 tasks) ===
    "runtime_play_and_inspect": (
        "Run the game and get the live game scene tree. "
        "Then STOP the game before finishing."
    ),
    "runtime_simulate_input": (
        "Run the game, simulate pressing the Space key, then stop the game."
    ),
    "runtime_performance": (
        "Run the game and read the runtime performance monitors. Then stop the game."
    ),
    "runtime_debugger_eval": (
        "Run the game, evaluate the expression '2+2' in the debugger, then stop."
    ),
    # === BATCH / PHYSICS / PROFILING (3 tasks) ===
    "batch_set_multiple": (
        "Create 2 Node2D nodes named 'BatchA' and 'BatchB'. "
        "Set both positions to (300, 300) in a single batch call. "
        "NOTE: If batch_set_property times out, use set_node_property instead."
    ),
    "physics_setup": (
        "Set the Background node's position to (100, 100) using set_node_property. "
        "Call with node_path='Background', property='position', value={'x': 100, 'y': 100}."
    ),
    "profiling_fps": ("Check the editor's current FPS. The game is NOT running."),
    # === END-TO-END WORKFLOWS (5 tasks) ===
    "workflow_create_character": (
        "Create a complete player character: create a CharacterBody2D named 'CharTest', "
        "attach a script at res://scripts/char_test.gd that extends CharacterBody2D, "
        "set its position to (100, 100), and save the scene."
    ),
    "workflow_script_and_play": (
        "Write a script to res://scripts/play_test.gd, attach it to "
        "the Player node, save, and run the game."
    ),
    "workflow_scene_hierarchy": (
        "Get the scene tree, find all nodes with CollisionShape2D, and report their parent nodes."
    ),
    "workflow_signal_and_test": (
        "Connect Player's 'ready' signal to Background's '_ready', "
        "save the scene, and run the game."
    ),
    "workflow_batch_mutation": (
        "Create 3 Sprite2D nodes, find them by type, then batch-set "
        "all their modulate colors to red (Color(1,0,0,1))."
    ),
}


# ---------------------------------------------------------------------------
# Expected first tools per task
# ---------------------------------------------------------------------------

EXPECTED_FIRST_TOOLS: dict[str, str] = {
    # Inspection
    "inspect_scene_tree": "get_scene_tree",
    "inspect_node_properties": "get_node_properties",
    "inspect_property_list": "get_node_property_list",
    "inspect_find_by_type": "find_nodes_by_type",
    # Mutation
    "mutate_create_and_property": "create_node",
    "mutate_delete_with_confirm": "delete_node",
    "mutate_rename": "create_node",
    "mutate_save_scene": "save_scene",
    "mutate_attach_script": "attach_script",
    # Scripts
    "script_write_and_read": "write_script",
    "script_patch": "read_script",
    "script_list": "list_scripts",
    "script_get_for_node": "get_script_for_node",
    # Scene
    "scene_list_and_open": "list_open_scenes",
    "scene_select_nodes": "select_nodes",
    # Signals
    "signal_connect_ready": "connect_signal",
    # Runtime
    "runtime_play_and_inspect": "play_scene",
    "runtime_simulate_input": "play_scene",
    "runtime_performance": "play_scene",
    "runtime_debugger_eval": "play_scene",
    # Batch/Physics/Profiling
    "batch_set_multiple": "create_node",
    "physics_setup": "set_node_property",
    "profiling_fps": "get_editor_performance",
    # Workflows
    "workflow_create_character": "create_node",
    "workflow_script_and_play": "write_script",
    "workflow_scene_hierarchy": "get_scene_tree",
    "workflow_signal_and_test": "connect_signal",
    "workflow_batch_mutation": "create_node",
}


# ---------------------------------------------------------------------------
# Optimal steps per task
# ---------------------------------------------------------------------------

OPTIMAL_STEPS: dict[str, int] = {
    # Inspection
    "inspect_scene_tree": 1,
    "inspect_node_properties": 1,
    "inspect_property_list": 2,
    "inspect_find_by_type": 1,
    # Mutation
    "mutate_create_and_property": 2,
    "mutate_delete_with_confirm": 1,
    "mutate_rename": 1,
    "mutate_save_scene": 1,
    "mutate_attach_script": 1,
    # Scripts
    "script_write_and_read": 2,
    "script_patch": 3,
    "script_list": 1,
    "script_get_for_node": 1,
    # Scene
    "scene_list_and_open": 2,
    "scene_select_nodes": 1,
    # Signals
    "signal_connect_ready": 1,
    # Runtime
    "runtime_play_and_inspect": 2,
    "runtime_simulate_input": 3,
    "runtime_performance": 3,
    "runtime_debugger_eval": 3,
    # Batch/Physics/Profiling
    "batch_set_multiple": 3,
    "physics_setup": 1,
    "profiling_fps": 1,
    # Workflows
    "workflow_create_character": 5,
    "workflow_script_and_play": 4,
    "workflow_scene_hierarchy": 2,
    "workflow_signal_and_test": 4,
    "workflow_batch_mutation": 4,
}


# ---------------------------------------------------------------------------
# Tool filtering per task: only expose relevant tools to reduce exploration
# ---------------------------------------------------------------------------

TASK_TOOL_FILTER: dict[str, list[str]] = {
    # Inspection
    "inspect_scene_tree": ["get_scene_tree", "find_nodes_by_type", "done"],
    "inspect_node_properties": ["get_node_properties", "get_scene_tree", "done"],
    "inspect_property_list": [
        "get_node_property_list",
        "set_node_property",
        "get_scene_tree",
        "done",
    ],
    "inspect_find_by_type": ["find_nodes_by_type", "get_scene_tree", "done"],
    # Mutation
    "mutate_create_and_property": [
        "create_node",
        "set_node_property",
        "get_scene_tree",
        "done",
    ],
    "mutate_delete_with_confirm": ["create_node", "delete_node", "get_scene_tree", "done"],
    "mutate_rename": [
        "create_node",
        "rename_node",
        "delete_node",
        "get_scene_tree",
        "done",
    ],
    "mutate_save_scene": ["save_scene", "done"],
    "mutate_attach_script": ["attach_script", "get_scene_tree", "done"],
    # Scripts
    "script_write_and_read": ["write_script", "read_script", "done"],
    "script_patch": ["read_script", "patch_script", "done"],
    "script_list": ["list_scripts", "done"],
    "script_get_for_node": ["get_script_for_node", "get_scene_tree", "done"],
    # Scene
    "scene_list_and_open": [
        "list_open_scenes",
        "open_scene",
        "save_all_scenes",
        "done",
    ],
    "scene_select_nodes": ["select_nodes", "get_scene_tree", "done"],
    # Signals
    "signal_connect_ready": ["connect_signal", "get_scene_tree", "done"],
    # Runtime
    "runtime_play_and_inspect": [
        "play_scene",
        "get_game_scene_tree",
        "stop_scene",
        "done",
    ],
    "runtime_simulate_input": [
        "play_scene",
        "simulate_key",
        "stop_scene",
        "done",
    ],
    "runtime_performance": [
        "play_scene",
        "get_performance_monitors",
        "stop_scene",
        "done",
    ],
    "runtime_debugger_eval": [
        "play_scene",
        "evaluate_expression",
        "stop_scene",
        "done",
    ],
    # Batch / Physics / Profiling
    "batch_set_multiple": [
        "create_node",
        "batch_set_property",
        "get_scene_tree",
        "done",
    ],
    "physics_setup": ["set_node_property", "done"],
    "profiling_fps": ["get_editor_performance", "done"],
    # Workflows
    "workflow_create_character": [
        "create_node",
        "write_script",
        "attach_script",
        "set_node_property",
        "save_scene",
        "done",
    ],
    "workflow_script_and_play": [
        "write_script",
        "attach_script",
        "save_scene",
        "play_scene",
        "stop_scene",
        "done",
    ],
    "workflow_scene_hierarchy": [
        "get_scene_tree",
        "find_nodes_by_type",
        "get_node_properties",
        "done",
    ],
    "workflow_signal_and_test": [
        "connect_signal",
        "save_scene",
        "play_scene",
        "stop_scene",
        "done",
    ],
    "workflow_batch_mutation": [
        "create_node",
        "find_nodes_by_type",
        "batch_set_property",
        "get_scene_tree",
        "done",
    ],
}


# ---------------------------------------------------------------------------
# LLM task execution
# ---------------------------------------------------------------------------


@dataclass
class LLMTaskResult:
    task_name: str
    steps: list[dict] = field(default_factory=list)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    score: TaskScore = field(default_factory=TaskScore)
    first_attempt_correct: bool = False
    errors: int = 0
    duration_ms: float = 0.0
    error_categories: list[str] = field(default_factory=list)
    notes: str = ""
    latency_profile: dict[str, dict[str, float | int]] = field(default_factory=dict)
    overall_latency: dict[str, float | int] = field(default_factory=dict)

    @property
    def step_count(self) -> int:
        return len(self.steps)


class LLMTaskRunner:
    def __init__(self, bridge: BridgeConnector, model: str = "qwen3-coder:30b") -> None:
        self._bridge = bridge
        self._model = model
        self._agent: OllamaAgent | None = None
        self._profiler = ToolProfiler()

    async def run_task(self, task_name: str, max_steps: int = 12) -> LLMTaskResult:
        result = LLMTaskResult(task_name=task_name)
        start = time.perf_counter()
        self._profiler.reset()

        await self._bridge.cleanup()

        base_prompt = TASK_PROMPTS.get(task_name, f"Complete the task: {task_name}")
        prompt = (
            f"{base_prompt}\n\n"
            "IMPORTANT: You MUST call one or more tools to complete this task. "
            "Do NOT return 'done' until you have successfully completed all required actions. "
            "Return ONLY a JSON object with the tool to call. "
            'When the task is COMPLETELY finished, return {"tool": "done"}.'
        )
        tools = get_available_tools()

        # Filter tools to only those relevant for this task
        allowed_names = set(TASK_TOOL_FILTER.get(task_name, []))
        allowed_names.add("done")  # Always allow done
        tools = [t for t in tools if t["name"] in allowed_names]

        self._agent = OllamaAgent(self._bridge._bridge, model=self._model)
        self._agent._history = []

        expected_first = EXPECTED_FIRST_TOOLS.get(task_name)

        # Track mutations for cleanup
        created_nodes: list[str] = []
        rename_stack: list[tuple[str, str]] = []  # (old_name, new_name)

        for step_num in range(max_steps):
            step_prompt = (
                prompt
                if step_num == 0
                else "Continue completing the task. Choose the next tool to call."
            )

            try:
                call = self._agent._ask(step_prompt, tools)
            except Exception as e:
                result.notes = f"LLM query failed: {e}"
                result.errors += 1
                result.error_categories.append("infrastructure")
                break

            result.token_usage.prompt_tokens += call.prompt_tokens
            result.token_usage.completion_tokens += call.completion_tokens
            result.token_usage.total_tokens += call.prompt_tokens + call.completion_tokens

            try:
                exec_result = await self._agent._execute(call)
            except Exception as e:
                exec_result = {
                    "ok": False,
                    "error": str(e),
                    "hint": "Execution failed",
                    "done": False,
                }

            self._agent._add_result(exec_result)

            step_record = {
                "step": step_num + 1,
                "tool": call.tool,
                "params": call.params,
                "reasoning": call.reasoning,
                "ok": exec_result.get("ok", False),
                "error": exec_result.get("error"),
                "hint": exec_result.get("hint"),
                "latency_ms": exec_result.get("latency_ms"),
            }
            result.steps.append(step_record)

            # Record latency in profiler
            if call.tool != "done":
                self._profiler.record(
                    call.tool,
                    latency_ms=exec_result.get("latency_ms", 0.0) or 0.0,
                    ok=exec_result.get("ok", False),
                )

            # Track created nodes and renames for cleanup
            if call.tool == "create_node" and exec_result.get("ok"):
                node_path = (
                    exec_result.get("result", {}).get("node_path", "")
                    or call.params.get("name", "")
                )
                if node_path:
                    created_nodes.append(node_path)
            elif call.tool == "rename_node" and exec_result.get("ok"):
                # Store (path_after_rename, original_name) for revert
                renamed_path = exec_result.get("result", {}).get("node_path", "")
                original_name = exec_result.get("result", {}).get("old_name", "")
                if renamed_path and original_name:
                    rename_stack.append((renamed_path, original_name))

            if step_num == 0 and expected_first:
                result.first_attempt_correct = call.tool == expected_first

            if not exec_result.get("ok", False):
                result.errors += 1
                category = ErrorTaxonomy.classify(
                    exec_result.get("error", ""),
                    exec_result.get("hint", ""),
                )
                result.error_categories.append(category)

            if call.tool == "done" or exec_result.get("done"):
                break

            if result.errors >= 4:
                result.notes = "Stopped: too many errors"
                break

        # Cleanup: delete created test nodes
        for node_path in created_nodes:
            try:
                await self._bridge.call(
                    "cmd_delete_node",
                    {"node_path": node_path, "confirm": True},
                )
            except Exception:
                pass  # Node may already be deleted or renamed

        # Cleanup: revert renames (in reverse order)
        for renamed_path, original_name in reversed(rename_stack):
            try:
                await self._bridge.call(
                    "cmd_rename_node",
                    {"node_path": renamed_path, "new_name": original_name},
                )
            except Exception:
                pass  # Node may no longer exist

        result.duration_ms = (time.perf_counter() - start) * 1000
        result.score = self._score_task(result, task_name)
        result.latency_profile = self._profiler.summary()
        result.overall_latency = self._profiler.overall()
        return result

    def _score_task(self, result: LLMTaskResult, task_name: str) -> TaskScore:
        score = TaskScore()
        real_steps = [s for s in result.steps if s["tool"] != "done"]

        last_ok = any(s["ok"] for s in real_steps)
        score.tool_choice = 1.0 if last_ok else 0.0
        score.prerequisites = 1.0 if result.first_attempt_correct else 0.0

        real_errors = [s for s in real_steps if not s["ok"]]
        if len(real_errors) == 0:
            score.recovery = 1.0
        elif any(s["ok"] for s in real_steps[1:]) and len(real_errors) > 0:
            score.recovery = 1.0
        else:
            score.recovery = 0.0

        optimal = OPTIMAL_STEPS.get(task_name, 3)
        real_step_count = len(real_steps)
        if real_step_count <= optimal:
            score.efficiency = 1.0
        else:
            ratio = (real_step_count - optimal) / optimal
            score.efficiency = max(0.0, 1.0 - ratio * 0.5)

        return score


# ---------------------------------------------------------------------------
# Suite orchestration
# ---------------------------------------------------------------------------

ALL_TASK_NAMES: list[str] = list(TASK_PROMPTS.keys())


async def run_llm_suite(
    tasks: list[str] | None = None,
    model: str = "qwen3-coder:30b",
    max_steps: int = 12,
) -> list[LLMTaskResult]:
    bridge = BridgeConnector()

    if not await bridge.connect():
        print("❌ Could not connect to Godot addon bridge. Is Godot running?")
        return []

    runner = LLMTaskRunner(bridge, model=model)
    task_list = tasks or ALL_TASK_NAMES
    results: list[LLMTaskResult] = []

    print(f"\n{'=' * 70}")
    print(f"  Expanded Real LLM Eval Suite v2 — {model}")
    print(f"  Tasks: {len(task_list)} | Max steps: {max_steps}")
    print(f"{'=' * 70}")

    for task_name in task_list:
        print(f"\n  [{task_name}]")
        try:
            result = await runner.run_task(task_name, max_steps=max_steps)
            results.append(result)

            s = result.score
            status = "PASS" if s.overall >= 0.7 else ("PARTIAL" if s.overall >= 0.4 else "FAIL")
            print(
                f"    {status} | overall={s.overall:.2f} | "
                f"choice={s.tool_choice:.1f} prereq={s.prerequisites:.1f} "
                f"recovery={s.recovery:.1f} eff={s.efficiency:.1f} | "
                f"steps={result.step_count} errors={result.errors}"
            )
            print(f"    First attempt: {'✅' if result.first_attempt_correct else '❌'}")
            if result.error_categories:
                cats = ", ".join(set(result.error_categories))
                print(f"    Error categories: {cats}")
            if result.notes:
                print(f"    Notes: {result.notes}")
            for step in result.steps:
                icon = "✅" if step["ok"] else "❌"
                print(f"      {icon} {step['step']}. {step['tool']}({json.dumps(step['params'])})")
        except Exception as e:
            print(f"    💥 EXCEPTION: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()

    await bridge.close()
    return results


def print_summary(results: list[LLMTaskResult]) -> None:
    if not results:
        print("No results.")
        return

    print("\n" + "=" * 70)
    print("  Expanded LLM Eval Summary v2")
    print("=" * 70)

    total_pass = total_partial = total_fail = 0
    total_first_correct = 0
    total_errors = 0
    total_steps = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0

    for r in results:
        s = r.score
        if s.overall >= 0.7:
            total_pass += 1
        elif s.overall >= 0.4:
            total_partial += 1
        else:
            total_fail += 1
        total_first_correct += 1 if r.first_attempt_correct else 0
        total_errors += r.errors
        total_steps += r.step_count
        total_prompt_tokens += r.token_usage.prompt_tokens
        total_completion_tokens += r.token_usage.completion_tokens

    mean_score = sum(r.score.overall for r in results) / len(results)
    compliance = total_pass / len(results)
    first_attempt = total_first_correct / len(results)

    all_categories = []
    for r in results:
        all_categories.extend(r.error_categories)
    cat_counts: dict[str, int] = {}
    for c in all_categories:
        cat_counts[c] = cat_counts.get(c, 0) + 1

    print(f"  Tasks evaluated: {len(results)}")
    print(f"  Mean overall score: {mean_score:.2f}")
    print(f"  Compliance rate: {compliance:.0%}")
    print(f"  First-attempt correct: {first_attempt:.0%}")
    print(f"  Total errors: {total_errors}")
    print(f"  Mean steps per task: {total_steps / len(results):.1f}")
    print(f"  Total prompt tokens: {total_prompt_tokens}")
    print(f"  Total completion tokens: {total_completion_tokens}")
    mean_tok = (total_prompt_tokens + total_completion_tokens) / len(results)
    print(f"  Mean tokens per task: {mean_tok:.0f}")

    if cat_counts:
        print("\n  Error taxonomy:")
        for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
            print(f"    {cat}: {count}")

    # Aggregate latency across all results
    all_tools: dict[str, list[dict]] = {}
    for r in results:
        for tool, stats in r.latency_profile.items():
            all_tools.setdefault(tool, []).append(stats)
    if all_tools:
        print("\n  Latency profile (per tool, aggregated across tasks):")
        for tool in sorted(all_tools.keys()):
            entries = all_tools[tool]
            total_count = sum(e["count"] for e in entries)
            mean_ms = round(
                sum(e["mean_ms"] * e["count"] for e in entries) / total_count, 2
            )
            max_ms = max(e["max_ms"] for e in entries)
            total_err = sum(e["error_rate"] * e["count"] for e in entries)
            err_rate = round(total_err / total_count, 3)
            print(
                f"    {tool}: n={total_count}, mean={mean_ms}ms, "
                f"max={max_ms}ms, errors={err_rate}"
            )
        overall = [r.overall_latency for r in results if r.overall_latency]
        if overall:
            total_calls = sum(o["total_calls"] for o in overall)
            grand_mean = round(
                sum(o["mean_ms"] * o["total_calls"] for o in overall) / total_calls, 2
            )
            print(f"  Overall: {total_calls} calls, mean={grand_mean}ms")

    print(f"\n  Breakdown: {total_pass} pass, {total_partial} partial, {total_fail} fail")
    print("=" * 70)


def log_results(
    results: list[LLMTaskResult],
    variant: str = "expanded-v2",
    model: str = "qwen3-coder:30b",
) -> None:
    tracker = EvalTracker()
    git_sha = get_git_sha()

    tracker.start_run(
        run_name=f"llm-eval-{variant}-{int(time.time())}",
        variant=variant,
    )

    tracker.log_param("model", model)
    tracker.log_param("git_sha", git_sha)
    tracker.log_param("variant", variant)
    tracker.log_param("task_count", len(results))

    if results:
        mean_score = sum(r.score.overall for r in results) / len(results)
        compliance = sum(1 for r in results if r.score.overall >= 0.7) / len(results)
        first_attempt = sum(1 for r in results if r.first_attempt_correct) / len(results)
        total_errors = sum(r.errors for r in results)
        total_steps = sum(r.step_count for r in results)
        total_prompt = sum(r.token_usage.prompt_tokens for r in results)
        total_completion = sum(r.token_usage.completion_tokens for r in results)

        tracker.log_metric("mean_score", mean_score)
        tracker.log_metric("compliance_rate", compliance)
        tracker.log_metric("first_attempt_rate", first_attempt)
        tracker.log_metric("total_errors", total_errors)
        tracker.log_metric("mean_steps", total_steps / len(results))
        tracker.log_metric("total_prompt_tokens", total_prompt)
        tracker.log_metric("total_completion_tokens", total_completion)
        tracker.log_metric("mean_tokens_per_task", (total_prompt + total_completion) / len(results))

        all_categories = []
        for r in results:
            all_categories.extend(r.error_categories)
        cat_counts: dict[str, int] = {}
        for c in all_categories:
            cat_counts[c] = cat_counts.get(c, 0) + 1
        for cat, count in cat_counts.items():
            tracker.log_metric(f"errors_{cat}", count)

        for r in results:
            s = r.score
            prefix = r.task_name
            tracker.log_metric(f"{prefix}_overall", s.overall)
            tracker.log_metric(f"{prefix}_tool_choice", s.tool_choice)
            tracker.log_metric(f"{prefix}_prerequisites", s.prerequisites)
            tracker.log_metric(f"{prefix}_recovery", s.recovery)
            tracker.log_metric(f"{prefix}_efficiency", s.efficiency)
            tracker.log_metric(f"{prefix}_steps", r.step_count)
            tracker.log_metric(f"{prefix}_errors", r.errors)
            tracker.log_metric(f"{prefix}_first_attempt", 1.0 if r.first_attempt_correct else 0.0)
            tracker.log_metric(f"{prefix}_prompt_tokens", r.token_usage.prompt_tokens)
            tracker.log_metric(f"{prefix}_completion_tokens", r.token_usage.completion_tokens)
            tracker.log_metric(f"{prefix}_duration_ms", r.duration_ms)
            # Log per-tool latency for this task
            for tool, stats in r.latency_profile.items():
                t_prefix = f"{prefix}_{tool}"
                tracker.log_metric(f"{t_prefix}_mean_ms", stats["mean_ms"])
                tracker.log_metric(f"{t_prefix}_count", stats["count"])
                if "p95_ms" in stats:
                    tracker.log_metric(f"{t_prefix}_p95_ms", stats["p95_ms"])
            if r.overall_latency:
                overall_mean = r.overall_latency.get("mean_ms", 0)
                overall_calls = r.overall_latency.get("total_calls", 0)
                tracker.log_metric(f"{prefix}_overall_mean_ms", overall_mean)
                tracker.log_metric(f"{prefix}_overall_calls", overall_calls)
            if r.notes:
                tracker.log_param(f"{prefix}_notes", r.notes[:250])

        # Log aggregate latency metrics
        if results:
            overall_latencies = [r.overall_latency for r in results if r.overall_latency]
            if overall_latencies:
                total_calls = sum(o["total_calls"] for o in overall_latencies)
                grand_mean = round(
                    sum(o["mean_ms"] * o["total_calls"] for o in overall_latencies) / total_calls, 2
                )
                tracker.log_metric("aggregate_mean_latency_ms", grand_mean)
                tracker.log_metric("aggregate_total_calls", total_calls)

    tracker.end_run()
    print("\n📊 Logged to MLFlow: https://mlflow.johndstudios.net/#/experiments/55")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Expanded real LLM eval for godot-mcp")
    parser.add_argument("--tasks", nargs="+", help="Specific tasks to run")
    parser.add_argument("--model", default="qwen3-coder:30b", help="Ollama model")
    parser.add_argument("--max-steps", type=int, default=12, help="Max steps per task")
    parser.add_argument("--variant", default="expanded-v2", help="Variant tag for MLFlow")
    args = parser.parse_args()

    results = await run_llm_suite(
        tasks=args.tasks,
        model=args.model,
        max_steps=args.max_steps,
    )
    print_summary(results)
    if results:
        log_results(results, variant=args.variant, model=args.model)


if __name__ == "__main__":
    asyncio.run(main())
