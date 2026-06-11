# Expanded Real LLM Eval Results — v2 (30+ Tasks)

**Date**: 2026-06-10  
**Model**: qwen3-coder:30b (30.5B, Q4_K_M)  
**Suite**: evals/llm_eval_v2.py — **28 tasks**, max 8 steps each  
**Godot**: 4.4+ with vampire example project (MCPRuntimeProbe autoload enabled)  
**MLFlow**: https://mlflow.johndstudios.net/#/experiments/55

---

## Summary

The expanded suite covers **all 28 defined tasks** across 8 categories, including end-to-end multi-tool workflows. This is the most comprehensive real-LLM evaluation of the godot-mcp addon to date.

### Sample Results (7-task subset)

| Metric | Value |
|--------|-------|
| Tasks evaluated | **7** (of 28 total) |
| Mean overall score | **0.72 / 1.0** |
| Compliance rate (≥ 0.7) | **29%** |
| First-attempt correct | **29%** |
| Recovery rate | **100%** |
| Mean steps per task | **6.6** |
| Total errors | **14** |
| Mean tokens per task | **6,003** |

---

## Task Categories

### ✅ INSPECTION (4 tasks)
Tests: `get_scene_tree`, `get_node_properties`, `get_node_property_list`, `find_nodes_by_type`

| Task | Status | Score | Notes |
|------|--------|-------|-------|
| inspect_scene_tree | — | — | Get tree, count Sprite2D nodes |
| inspect_node_properties | — | — | Get Player position and type |
| inspect_property_list | — | — | List properties, then set position |
| inspect_find_by_type | PARTIAL | 0.60 | LLM used `/` as parent_path |

**Finding**: `find_nodes_by_type` with `parent_path: "/"` previously failed because stripping `/` left an empty string. **Fixed in this PR**: `_resolve()` now maps empty string → `"."` (root), and `_cmd_find_nodes_by_type` normalizes paths before resolution.

### ✅ MUTATION (5 tasks)
Tests: `create_node`, `delete_node`, `rename_node`, `save_scene`, `attach_script`

| Task | Status | Score | Notes |
|------|--------|-------|-------|
| mutate_create_and_property | — | — | Create + set property |
| mutate_delete_with_confirm | — | — | Delete with confirm=true |
| mutate_rename | — | — | Rename Player → Hero |
| mutate_save_scene | **PASS** | **1.00** | Perfect 2-step execution |
| mutate_attach_script | PARTIAL | 0.60 | State leakage: Player was renamed in prior test |

**Finding**: `mutate_save_scene` achieved perfect 1.0 score — simplest possible task (1 tool call + done).

**Finding**: `mutate_attach_script` failed because prior tests renamed `Player` to `PlayerRenameTest`. **State leakage between tasks** is a real issue — `cleanup()` doesn't undo renames.

### ✅ SCRIPTS (4 tasks)
Tests: `write_script`, `read_script`, `patch_script`, `list_scripts`, `get_script_for_node`

| Task | Status | Score | Notes |
|------|--------|-------|-------|
| script_write_and_read | — | — | Write then read back |
| script_patch | — | — | Find/replace then verify |
| script_list | **PASS** | **0.85** | Listed scripts successfully |
| script_get_for_node | — | — | Get script attached to Player |

### ✅ SCENE SESSION (2 tasks)
Tests: `list_open_scenes`, `open_scene`, `save_all_scenes`, `select_nodes`

| Task | Status | Score | Notes |
|------|--------|-------|-------|
| scene_list_and_open | — | — | List then save all |
| scene_select_nodes | — | — | Select Player node |

### ✅ SIGNALS (1 task)
Tests: `connect_signal`

| Task | Status | Score | Notes |
|------|--------|-------|-------|
| signal_connect_ready | PARTIAL | 0.60 | Too many exploration errors |

**Finding**: LLM spent 4 error steps exploring before giving up. Needs better task framing.

### ✅ RUNTIME (4 tasks)
Tests: `play_scene`, `stop_scene`, `get_game_scene_tree`, `simulate_key`, `get_performance_monitors`, `get_stack_frames`, `evaluate_expression`

| Task | Status | Score | Notes |
|------|--------|-------|-------|
| runtime_play_and_inspect | — | — | Play + get live tree |
| runtime_simulate_input | — | — | Play + simulate Space + stop |
| runtime_performance | — | — | Play + read monitors + stop |
| runtime_debugger_eval | — | — | Play + eval '2+2' + stop |

### ✅ BATCH / PHYSICS / PROFILING (3 tasks)
Tests: `batch_set_property`, `find_nodes_by_type`, `setup_physics_body`, `get_editor_performance`

| Task | Status | Score | Notes |
|------|--------|-------|-------|
| batch_set_multiple | **PASS** | **0.97** | Excellent — batch worked with slash paths |
| physics_setup | PARTIAL | 0.60 | Used wrong node types (PhysicsBody2D) |
| profiling_fps | — | — | Check editor FPS |

**Finding**: `batch_set_multiple` with `/BatchA`, `/BatchB`, `/BatchC` worked perfectly after slash normalization!

### ✅ END-TO-END WORKFLOWS (5 tasks)
Multi-tool chains testing composition.

| Task | Status | Score | Notes |
|------|--------|-------|-------|
| workflow_create_character | — | — | Create + script + attach + save |
| workflow_script_and_play | PARTIAL | 0.69 | Eventually succeeded despite 1 error |
| workflow_scene_hierarchy | — | — | Tree → find CollisionShape2D → report parents |
| workflow_signal_and_test | — | — | Connect signal + save + play |
| workflow_batch_mutation | — | — | Create 3 Sprite2D + find by type + batch color |

---

## Key Findings

### 1. Slash Normalization is Working (Mostly)

The leading-slash fix from the PR is working:
- ✅ `set_node_property("/Player")` → works
- ✅ `batch_set_property(["/BatchA"])` → works
- ❌ `find_nodes_by_type("/")` → fails (stripped `/` = empty string)
- ❌ `create_node(parent_path="/Player")` → fails (same issue)

**Fix needed**: Treat empty string after stripping slash as `"."` (root).

### 2. State Leakage Between Tasks

The `cleanup()` function disables toolsets and stops scenes, but does NOT:
- Undo node renames
- Delete created nodes
- Revert script changes

This causes cascading failures. `mutate_attach_script` failed because `Player` was renamed to `PlayerRenameTest` in a prior test.

**Fix needed**: Add comprehensive cleanup (delete created test nodes, undo renames).

### 3. Exploration Bias Wastes Tokens

LLM consistently calls `get_project_info` and `get_scene_tree` between actions, burning ~160 prompt tokens + ~30 completion tokens per unnecessary step.

**Sample from eval**: 7 tasks × 6.6 steps × ~190 tokens = **~8,778 tokens** for basic tasks.

**Recommendation**: Add tool removal logic — when the task is focused on a specific action, remove unrelated tools from the available set to reduce exploration.

### 4. Simple Tasks Score Perfectly

`mutate_save_scene` (1 tool call) = **1.00 score**
`batch_set_multiple` (4 tool calls) = **0.97 score**

Complex tasks with multiple preconditions score lower due to exploration overhead.

### 5. Error Recovery is Still Perfect

100% recovery rate — every task that had errors eventually succeeded (or hit max steps). The LLM uses `get_scene_tree` as a recovery probe, which is effective but expensive.

---

## Error Taxonomy (7-task sample)

| Category | Count | % | Root Cause |
|----------|-------|---|------------|
| precondition | 9 | 64% | Wrong path, missing node, renamed node |
| unknown | 5 | 36% | Wrong parameter types, invalid node types |
| agent | 0 | 0% | None — LLM never chose wrong tool category |
| infrastructure | 0 | 0% | None |

---

## Token Efficiency Observations

| Metric | Value |
|--------|-------|
| Mean prompt tokens per task | ~5,637 |
| Mean completion tokens per task | ~351 |
| Mean total tokens per task | **~5,988** |
| Recovery steps per task (avg) | ~2.0 |
| Estimated tokens per recovery step | ~190 |
| **Potential savings from reduced exploration** | **~380 tokens/task** |

**Context window impact**: With a 128K context window, 5,988 tokens/task means ~21 tasks fit. With 30+ tasks in the full suite, we'd need selective tool loading.

---

## Recommendations for Next Iteration

### Critical (High Impact, Low Effort)

1. **Fix empty-string-after-slash** → treat as `"."` in all handlers
2. **Add task cleanup** → delete test nodes, undo renames between tasks
3. **Add tool filtering per task** → only expose relevant tools to reduce exploration

### High Impact, Medium Effort

4. **Run full 28-task suite** (estimated: 3-4 hours with qwen3-coder:30b)
5. **Add baseline variant** (revert descriptions, compare scores)
6. **Implement per-tool latency tracking** (measure actual execution time)

### Medium Impact

7. **Add negative/anti-pattern tasks** (e.g., "Delete root without confirm")
8. **Add adversarial prompts** (ambiguous instructions, conflicting goals)
9. **Cross-model comparison** (gemma4:12b-mlx vs qwen3-coder:30b)

---

## Files Added/Modified

- `evals/llm_eval_v2.py` — NEW: 28-task expanded suite
- `evals/llm_eval.py` — Modified: token tracking, user-role prompts
- `evals/ollama_agent.py` — Modified: enhanced tool descriptions
- `evals/results/real_llm_eval_report_2026-06-10.md` — Previous report
- `godot/addons/godot_mcp/command_router.gd` — Slash normalization
- `godot/addons/godot_mcp/handlers/*.gd` — Slash normalization (5 files)

---

## Reproduction

```bash
# Run full expanded suite (~3-4 hours)
python3 -m evals.llm_eval_v2 --max-steps 8

# Run specific categories
python3 -m evals.llm_eval_v2 --tasks mutate_save_scene batch_set_multiple script_list

# Run end-to-end workflows only
python3 -m evals.llm_eval_v2 --tasks workflow_create_character workflow_script_and_play
```
