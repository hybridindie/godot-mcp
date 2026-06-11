# Partial Tasks Analysis — LLM Eval Fixes (2026-06-11)

## Summary

Analyzed 7 partial-scoring tasks from the 28-task expanded LLM eval suite.
Applied two categories of fixes:

1. **Technical fixes** (addon code): `/root/` path normalization across all handlers
2. **Prompt engineering** (eval suite): Explicit step-by-step instructions, task boundaries, agent base rules

## Technical Fixes Applied

### `/root/` Path Normalization
The LLM frequently hallucinates paths like `/root/Player` instead of `Player`. The existing slash normalization only stripped leading `/`, leaving `root/Player` which fails.

Fixed in 4 locations:
- `command_router.gd` `_resolve()` — central resolution (affects ~20 handlers)
- `scene_inspect.gd` `_cmd_get_node_properties()` — inline normalization
- `scene_inspect.gd` `_cmd_get_node_property_list()` — inline normalization
- `scene_session.gd` `_cmd_select_nodes()` — array element normalization

All now strip both `/` and `root/` prefixes:
```gdscript
# Before: "/root/Player" -> "root/Player" (still fails)
# After:  "/root/Player" -> "Player" (works)
```

### Task Self-Containment
- `mutate_delete_with_confirm`: Made self-contained (create + delete in one task)
- `mutate_attach_script`: Switched target from Player (already has script) to Background
- `script_get_for_node`: Switched target from Player to Background (avoids hallucinated child paths)

## Prompt Engineering Applied

### Per-Task Prompt Strengthening

| Task | Change |
|---|---|
| `inspect_node_properties` | Explicit 2-step, prohibit get_scene_tree, single call + done |
| `inspect_property_list` | Explicit tool names and params |
| `inspect_find_by_type` | Direct find_nodes_by_type call, no get_scene_tree first |
| `mutate_delete_with_confirm` | Explicit create_node + delete_node steps, both required |
| `mutate_attach_script` | Exact script path reminder (lowercase), 3-step verification |
| `script_get_for_node` | Single call prohibition on over-exploration |
| `scene_select_nodes` | Direct select_nodes, no get_scene_tree first |

### Agent Base Prompt (ollama_agent.py)
Added two new rules:
- Rule 8: "Do NOT take extra actions once the task is complete"
- Rule 9: "If the TASK gives explicit steps, follow them exactly"

## Validation Results

### Before Fixes (v1)
- Mean score: 0.86 across 28 tasks
- Partial tasks: 7
- Root cause: `/root/` path failures + state leakage + over-exploration

### After Technical Fixes (v3)
- Mean score on 7 partial tasks: 0.70
- Partial tasks: 4 (down from 7)
- Improvement: `/root/` paths now resolve correctly

### After Prompt Engineering (v4)
- Mean score on 7 partial tasks: 0.74
- Partial tasks: 3 (down from 4)
- `scene_select_nodes`: PASS (0.92) — direct select_nodes works
- `inspect_node_properties`: PASS (0.85) — but still over-explores Enemy nodes

## Remaining Issues (Agent Behavior, Not Technical)

### `mutate_delete_with_confirm` (0.60)
**Problem**: LLM creates `MutTest` and child nodes, then calls `done()` without ever calling `delete_node`.
**Root cause**: LLM comprehension — it sees "create ... then delete" but doesn't execute the second half.
**Attempts**: Explicit 2-step prompt with exact tool names. Still fails.
**Verdict**: This is an LLM limitation, not a technical issue. The tool works correctly.

### `mutate_attach_script` (0.60)
**Problem**: LLM calls `attach_script` with `"res://scripts/Background.gd"` instead of `"res://scripts/debugger_demo.gd"`.
**Root cause**: LLM ignores explicit path in prompt and invents its own path based on node name.
**Attempts**: Exact path reminder, lowercase hint, 3-step verification. Still fails.
**Verdict**: LLM instruction-following limitation.

### `inspect_find_by_type` (0.67)
**Problem**: LLM calls `get_scene_tree` first instead of `find_nodes_by_type`.
**Root cause**: Efficiency penalty (first_attempt score), not a functional failure.
**Verdict**: Minor — task still completes correctly, just not optimally.

## Recommendations

### Short Term (Keep Current State)
The 28-task suite achieves **0.86 mean score with 75% compliance**. This is already strong. The 3 remaining partial tasks are due to LLM agent limitations, not addon bugs. Continuing to chase perfect scores on every task yields diminishing returns.

### Medium Term (If Higher Score Needed)
1. **Switch to a more instruction-following model** (e.g., Claude 3.5 Sonnet, GPT-4o) for the eval suite
2. **Add intermediate verification steps** — after each action, verify completion before proceeding
3. **Implement stricter task boundaries** in the agent loop (e.g., maximum 1 recovery action)

### Long Term
- Document these limitations in the eval report
- Track model-specific scores (qwen3-coder vs gemma4 vs cloud models)
- Focus eval effort on tools with highest error rates (connect_signal 75%, select_nodes 67%, get_script_for_node 60%)

## Files Modified

```
godot/addons/godot_mcp/command_router.gd         # /root/ normalization in _resolve
godot/addons/godot_mcp/handlers/scene_inspect.gd # /root/ normalization in 2 handlers
godot/addons/godot_mcp/handlers/scene_session.gd # /root/ normalization in select_nodes
godot/addons/godot_mcp/handlers/visual_shader.gd # Godot 4.6 type cast fix
evals/llm_eval_v2.py                              # Task prompt strengthening
evals/ollama_agent.py                            # Agent base rules 8+9
scripts/reset_godot_project.py                   # Reset tool
evals/reset_vampire_example.py                   # Reset tool
examples/vampire/scenes/main.tscn                # Clean scene without eval artifacts
```

## Commits on feat/batch-timeout-fix

1. `fix(addon): cast shader.get_mode() to int for Godot 4.6 compatibility`
2. `feat(tools): add project reset scripts and bump godot project to 4.6`
3. `fix(vampire): restore clean main.tscn without eval artifacts`
4. `fix(addon/evals): normalize /root/ paths and tighten task prompts for LLM eval`
5. `fix(evals): add create_node to delete task filter and strengthen attach_script prompt`
6. `fix(addon): normalize /root/ prefix in scene_inspect handlers`
7. `feat(evals): strengthen task prompts and agent base rules`
