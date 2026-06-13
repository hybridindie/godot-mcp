# Cross-Model Comparison Report: qwen3-coder:30b vs qwen3-coder:480b-cloud

**Date**: 2026-06-11  
**Suite**: 28-task expanded LLM eval (godot-mcp)  
**Max steps**: 12 per task

---

## Aggregate Results

| Metric | qwen3-coder:30b (local) | qwen3-coder:480b-cloud | Delta |
|--------|------------------------|------------------------|-------|
| **Mean overall score** | **0.87** | **0.87** | 0.00 |
| **Compliance rate** | 86% | 86% | 0% |
| **First-attempt correct** | 82% (23/28) | 82% (23/28) | 0% |
| **Pass / Partial / Fail** | 24 / 4 / 0 | 24 / 3 / 1 | — |
| **Total errors** | 16 | 17 | +1 |
| **Mean steps/task** | 4.4 | 4.4 | 0.0 |
| **Total prompt tokens** | 59,106 | 59,749 | +643 |
| **Total completion tokens** | 6,919 | 6,102 | −817 |
| **Mean tokens/task** | 2,358 | 2,352 | −6 |
| **Total tool calls** | 96 | 97 | +1 |
| **Mean latency/call** | 53.7ms | 70.0ms | +16.3ms |

**Verdict**: Statistically identical aggregate performance. The 480b-cloud model is ~30% slower per call (70ms vs 54ms) due to network round-trips, but uses slightly fewer completion tokens.

---

## Per-Task Comparison

### Where 480b-cloud wins (⬆️)

| Task | 30b | 480b | Delta | Why |
|------|-----|------|-------|-----|
| `workflow_signal_and_test` | 0.40 | **1.00** | **+0.60** | 480b recovers from connect_signal error and completes the workflow (save→play→stop). 30b gives up after 3 failed signal attempts. |
| `inspect_find_by_type` | 0.67 | **0.92** | **+0.25** | 480b calls `find_nodes_by_type` directly. 30b calls `get_scene_tree` first (suboptimal but works). |
| `runtime_debugger_eval` | 0.75 | **0.97** | **+0.22** | 480b uses creative expressions: `get_tree().get_nodes_in_group("enemies").size()` and `get_node("/root/Main").get_child_count()`. 30b fails twice on `Player.position`. |
| `profiling_fps` | 0.85 | **1.00** | **+0.15** | 480b calls `get_editor_performance` once and done. 30b calls it 3× (over-exploration). |
| `physics_setup` | 0.85 | **0.92** | **+0.07** | 480b stops after 3 steps (2 successful sets). 30b tries Enemy and UI/ScoreLabel which don't exist. |
| `inspect_scene_tree` | 0.85 | **0.92** | **+0.07** | 480b uses 3 steps vs 30b's 5 (less over-exploration with find_nodes_by_type). |

### Where 30b local wins (⬇️)

| Task | 30b | 480b | Delta | Why |
|------|-----|------|-------|-----|
| `scene_select_nodes` | **0.85** | 0.40 | **+0.45** | 480b **LLM query timed out** (infra error, not model fault). 30b completes in 8 steps. |
| `mutate_attach_script` | **0.60** | 0.35 | **+0.25** | 480b hallucinates non-existent `create_file` tool after attach_script fails. 30b just uses wrong path (`Background.gd` vs `debugger_demo.gd`) but valid tool. |
| `scene_list_and_open` | **1.00** | 0.75 | **+0.25** | 480b **LLM query timed out** on step 2. 30b completes cleanly. |
| `batch_set_multiple` | **0.97** | 0.85 | **+0.12** | 480b wastes steps with bad paths (`/root/BatchA`, `/root`) then hits max steps (12). 30b completes in 5 steps. |
| `mutate_rename` | **0.92** | 0.85 | **+0.07** | 480b adds unnecessary `delete_node` step after rename. 30b just creates+renames. |

### Identical performance (=)

| Task | Score | Notes |
|------|-------|-------|
| `inspect_node_properties` | 0.85 both | Both over-explore Background→Player→Enemy (which doesn't exist) |
| `script_get_for_node` | 0.85 both | Both check Background→Player→Enemy (doesn't exist) |
| `script_write_and_read` | 1.00 both | Perfect |
| `script_list` | 1.00 both | Perfect |
| `script_patch` | 0.75 both | Both skip `read_script` first (first-attempt ❌) but patch succeeds |
| `mutate_create_and_property` | ~1.00 both | Nearly perfect |
| `mutate_save_scene` | 1.00 both | Perfect |
| `mutate_delete_with_confirm` | 0.60 both | **Both fail identically**: create `MutTest` + children, then call `done()` without ever calling `delete_node`. This is an LLM comprehension limitation, not a tool issue. |
| `runtime_play_and_inspect` | 1.00 both | Perfect |
| `runtime_simulate_input` | ~1.00 both | Perfect |
| `runtime_performance` | 1.00 both | Perfect |
| `workflow_create_character` | ~0.97 both | 480b makes script path error then recovers; 30b is cleaner |
| `workflow_script_and_play` | 1.00 both | Perfect |
| `workflow_scene_hierarchy` | 0.85 both | Both get stuck on non-existent nodes (Enemy, StaticBody2D) |
| `workflow_batch_mutation` | 1.00 both | Perfect |

---

## Error Taxonomy Comparison

| Category | 30b (local) | 480b (cloud) | Notes |
|----------|-------------|--------------|-------|
| **precondition** | 7 | 9 | 480b makes more "node not found" attempts |
| **unknown** | 9 | 5 | 30b has more unexplained addon failures |
| **infrastructure** | 0 | 2 | 480b: 2× LLM timeout (120s limit) |
| **agent** | 0 | 1 | 480b: 1× tool hallucination (`create_file`) |

---

## Behavioral Patterns

### 480b-cloud strengths
1. **Better creative problem-solving**: Uses more sophisticated debugger expressions
2. **Faster abandonment of failing approaches**: Stops sooner when a path isn't working
3. **More concise scene tree exploration**: Less redundant `get_scene_tree` calls

### 480b-cloud weaknesses
1. **Timeout vulnerability**: 2 tasks failed due to 120s HTTP timeout (cloud latency + queuing)
2. **Tool hallucination risk**: When stuck, invents non-existent tools (`create_file`)
3. **Over-corrects on batch tasks**: Tries many path variations (`/root/BatchA`, `/root`, `.`) before finding the right one

### 30b local strengths
1. **No timeout issues**: Local inference is fast enough for the 120s limit
2. **More conservative**: Sticks to known tools, doesn't hallucinate
3. **Deterministic**: Slightly more predictable step patterns

### 30b local weaknesses
1. **Over-exploration**: Calls `get_editor_performance` 3×, tries multiple node types unnecessarily
2. **Less creative debugging**: Fails on simple `Player.position` expression

---

## Key Prompt/Tool Description Gaps Identified

Based on where BOTH models fail, these are the highest-impact improvements:

### 1. `mutate_delete_with_confirm` — Both score 0.60
**Problem**: LLM creates `MutTest` + children, then calls `done()` without ever deleting.  
**Root cause**: The prompt says "create ... then delete" but the LLM doesn't execute the second half. This is a **task comprehension** issue, not a tool issue.  
**Recommendation**: Add explicit intermediate verification — after create, the agent must confirm existence before proceeding to delete. Or split into two separate eval tasks.

### 2. `mutate_attach_script` — Both score ≤0.60
**Problem**: Both models ignore the explicit script path `res://scripts/debugger_demo.gd` and invent their own (`Background.gd`, `background.gd`, `CharTest.gd`).  
**Root cause**: The prompt explicitly states the path, but the LLM substitutes based on node name. This is an **instruction-following** failure.  
**Recommendation**: Strengthen the prompt with: "You MUST use the EXACT script path provided: res://scripts/debugger_demo.gd. Do NOT change this path."

### 3. `scene_select_nodes` — 480b timeout, 30b over-explores
**Problem**: 480b times out; 30b calls `get_scene_tree` then tries child nodes (`Player/AnimationPlayer`, `Player/AnimationTreePlayer`) which don't exist.  
**Root cause**: The task prompt says "Do NOT call get_scene_tree first" but the LLM does it anyway. Also the task is too simple (just select Player) so the LLM looks for additional work.  
**Recommendation**: Remove the prohibition on `get_scene_tree` — it's natural for the agent to verify. Or make the task more complex (select multiple specific nodes).

### 4. `workflow_scene_hierarchy` — Both 0.85
**Problem**: Both get stuck trying to access `Enemy/CollisionShape2D` and `StaticBody2D/CollisionShape2D` which don't exist in the test scene.  
**Root cause**: The task assumes a scene structure that isn't present.  
**Recommendation**: Make the task self-contained — create the nodes first, then query them. Or add a `get_scene_tree` precondition check to the task prompt.

### 5. `connect_signal` — Both fail (75-100% error rate)
**Problem**: `connect_signal` fails consistently even though parameters look correct.  
**Root cause**: Likely an addon-side issue with signal name or method existence (`_ready` may not be a valid target method).  
**Recommendation**: Check the addon handler — this may be a real bug, not an LLM issue.

### 6. `enable_toolset` hallucination (5-task subset only)
**Problem**: Both models call `enable_toolset` which doesn't exist in the tool list.  
**Root cause**: The system prompt says "Follow the MANDATORY PROTOCOL: enable_toolset first, then use tools." This is **outdated** — there's no such tool.  
**Recommendation**: Remove rule #2 from `_system_prompt()` in `ollama_agent.py` and `cloud_client.py`.

---

## Recommended Fixes (by impact)

| Priority | Fix | File | Expected improvement |
|----------|-----|------|---------------------|
| 🔴 High | Remove `enable_toolset` from system prompt | `evals/ollama_agent.py`, `evals/cloud_client.py` | +0.15 on tasks that hallucinate this tool |
| 🔴 High | Strengthen `mutate_attach_script` with "EXACT path" constraint | `evals/llm_eval_v2.py` TASK_PROMPTS | +0.25 on this task |
| 🟡 Medium | Fix `connect_signal` addon handler or task parameters | `godot/addons/godot_mcp/handlers/` | +0.40 on signal tasks |
| 🟡 Medium | Split `mutate_delete_with_confirm` or add explicit intermediate step | `evals/llm_eval_v2.py` | +0.40 on this task |
| 🟢 Low | Make `workflow_scene_hierarchy` self-contained | `evals/llm_eval_v2.py` | +0.15 on this task |
| 🟢 Low | Remove "Do NOT call get_scene_tree" prohibitions | `evals/llm_eval_v2.py` | Reduces unnecessary errors |

---

## MLFlow Run IDs

- **30b local**: `llm-eval-full-30b-{timestamp}`
- **480b cloud**: `llm-eval-full-480b-cloud-{timestamp}`
- **Experiment**: https://mlflow.johndstudios.net/#/experiments/55

---

*Generated by cross_model_compare.py on 2026-06-11*
