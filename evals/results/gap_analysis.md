# MCP Evals Gap Analysis & Research Roadmap

**Date**: 2026-06-10  
**Current State**: Evals measure infrastructure (4/13 pass) and simulated agent behavior (0.74/1.0 mean score)  
**Goal**: Identify all missing vectors that could improve accuracy and reduce tool-use turns

---

## Current Eval Coverage

| Dimension | Measured | Score |
|-----------|----------|-------|
| Tool existence (can it be called?) | ✅ | 4/13 |
| Agent tool choice correctness | ✅ | 0.74/1.0 |
| Agent prerequisite compliance | ✅ | 0.25/1.0 |
| Agent error recovery | ✅ | 1.00/1.0 |
| Agent efficiency (steps vs optimal) | ✅ | 0.80/1.0 |
| **Actual LLM behavior** | ❌ | N/A |
| **Token cost** | ❌ | N/A |
| **End-to-end workflows** | ❌ | N/A |
| **Description variant impact** | ❌ | N/A |
| **Cross-tool composition** | ❌ | N/A |
| **Failure taxonomy** | ❌ | N/A |
| **Regression tracking** | ❌ | N/A |
| **Performance/latency** | ❌ | N/A |
| **Real-world task complexity** | ❌ | N/A |

---

## Missing Vector 1: Real LLM Agent Evaluation

**Problem**: Our agent suite simulates agent logic with hardcoded sequences. It does NOT test whether an actual LLM (Claude, GPT-4, qwen-coder) reads the descriptions and makes correct decisions.

**Impact**: HIGH — We don't know if our description improvements actually help real LLMs.

**Implementation**: 
- Use `evals/ollama_agent.py` as foundation
- Add system prompts with/without decision tree
- Measure first-attempt correctness with real qwen-coder:30b
- A/B test: baseline descriptions vs post-PR descriptions

**Metrics**:
- `first_attempt_correct` (tool_choice on first call)
- `recovery_steps` (how many turns to recover from error)
- `token_usage` (total prompt + completion tokens)
- `hallucination_rate` (does LLM invent non-existent tools?)

---

## Missing Vector 2: Token & Cost Efficiency

**Problem**: We track "steps" but not actual LLM tokens. A step could be 1 token (simple tool call) or 500 tokens (complex reasoning + parameter construction).

**Impact**: MEDIUM — Helps optimize for production cost.

**Implementation**:
- Integrate with Ollama API to capture `prompt_tokens` and `completion_tokens`
- Add `token_efficiency` = tokens per successful tool call
- Track cost per task (for cloud LLMs: GPT-4, Claude)

**Metrics**:
- `tokens_per_step`
- `tokens_per_task`
- `cost_per_task` (for cloud APIs)
- `prompt_tokens` vs `completion_tokens` ratio

---

## Missing Vector 3: End-to-End Workflow Evaluation

**Problem**: We test individual tools in isolation. No test covers a realistic multi-step workflow like "Create a player character with physics, attach a script, and run the game."

**Impact**: HIGH — Real agents perform workflows, not single tool calls.

**Implementation**:
- Define 5 realistic workflows:
  1. "Create a simple platformer level"
  2. "Debug a script error using breakpoints"
  3. "Add UI with buttons and connect signals"
  4. "Set up physics collision for a character"
  5. "Import an asset and use it in a scene"
- Each workflow is a sequence of 5–15 tool calls
- Measure completion rate, steps, errors, and recovery

**Metrics**:
- `workflow_completion_rate`
- `workflow_steps` (total turns)
- `workflow_errors` (unrecoverable failures)
- `workflow_duration_ms`

---

## Missing Vector 4: Description Variant A/B Testing

**Problem**: We defined 4 variants (baseline, concise, structured, agent_optimized) but never actually swap them and measure impact.

**Impact**: HIGH — We don't know which description style works best.

**Implementation**:
- Monkey-patch `mcp_server/tools/*.py` docstrings at runtime
- Run identical tasks with each variant
- Log variant-tagged metrics to MLFlow
- Statistical significance testing (n=30 runs per variant)

**Variants to Test**:
| Variant | Hypothesis | Expected Winner For |
|---------|-----------|---------------------|
| baseline | Current descriptions | Control |
| concise | Shorter = less noise | Simple tools |
| structured | WHEN/RETURNS sections | Complex tools |
| agent_optimized | "Call this when..." | Multi-step tasks |

**Metrics**:
- `completion_rate_delta` vs baseline
- `mean_steps_delta` vs baseline
- `first_attempt_delta` vs baseline
- `p_value` (statistical significance)

---

## Missing Vector 5: Cross-Tool Composition Testing

**Problem**: We test tools in isolation. No test verifies that tool outputs feed correctly into subsequent tool inputs.

**Impact**: MEDIUM — Prevents integration failures.

**Example Chain**:
1. `get_scene_tree()` → extract node path
2. `get_node_property_list(path)` → extract property name
3. `set_node_property(path, prop, value)` → mutate

**Failure Modes**:
- Path format mismatch (`/root/Player` vs `./Player`)
- Property type mismatch (Vector2 vs dict)
- Node lifetime (node freed between steps)

**Metrics**:
- `chain_success_rate`
- `chain_breakpoint` (which step fails)
- `output_format_compliance`

---

## Missing Vector 6: Failure Taxonomy & Root Cause Analysis

**Problem**: We track "errors" but don't categorize them. We can't distinguish between:
- Agent error (wrong tool choice)
- Precondition error (missing play session)
- Infrastructure error (bridge disconnected)
- Bug in tool implementation

**Impact**: MEDIUM — Helps prioritize fixes.

**Taxonomy**:
```
Error Category:
├── Agent Error
│   ├── Wrong tool for intent
│   ├── Wrong parameter format
│   ├── Missing prerequisite step
│   └── Hallucinated tool name
├── Precondition Error
│   ├── No active scene
│   ├── No play session
│   ├── Toolset not enabled
│   └── Node not found
├── Infrastructure Error
│   ├── Bridge disconnected
│   ├── Godot not running
│   ├── Addon not enabled
│   └── Timeout
└── Tool Bug
    ├── Crash in handler
    ├── Wrong return type
    └── Side effect not undone
```

---

## Missing Vector 7: Performance & Latency Profiling

**Problem**: No measurement of actual tool execution time. Slow tools degrade agent experience.

**Impact**: MEDIUM — Latency affects agent responsiveness.

**Metrics**:
- `tool_latency_ms` (round-trip time)
- `addon_handler_time_ms` (Godot-side processing)
- `serialization_overhead_ms` (JSON encode/decode)
- `bridge_wait_time_ms` (async queue depth)

---

## Missing Vector 8: Instruction Staleness Detection

**Problem**: Tool descriptions may drift from actual implementation. E.g., a docstring says "requires play session" but the tool actually works without it after a recent change.

**Impact**: LOW — But causes agent confusion.

**Implementation**:
- Static analysis: parse docstrings, extract requirements
- Runtime verification: test each requirement in isolation
- Report drift: "Docstring claims 'requires play session' but tool works without it"

---

## Missing Vector 9: Regression Tracking Over Time

**Problem**: We have single-point measurements but no time series. Can't detect "this worked last week but fails now."

**Impact**: MEDIUM — Prevents silent regressions.

**Implementation**:
- Store historical results in MLFlow with `git_sha` param
- Run nightly CI evals
- Alert on delta > 0.1 for any metric

---

## Missing Vector 10: Toolset Transition Costs

**Problem**: No measurement of the friction when switching between toolsets. E.g., cost of `enable_toolset('physics')` when agent was using `scene_edit`.

**Impact**: LOW — But affects multi-domain workflows.

**Metrics**:
- `enable_toolset_latency_ms`
- `context_switch_steps` (extra steps to orient in new toolset)
- `forgetting_rate` (does agent re-enable already-enabled toolset?)

---

## Recommended Implementation Order

### Phase 1 (High Impact, Low Effort)
1. **Real LLM evaluation** — Wire up qwen-coder:30b to agent_suite_v2
2. **Token tracking** — Capture Ollama API token counts
3. **Failure taxonomy** — Categorize all errors in agent_suite_v2

### Phase 2 (High Impact, Medium Effort)
4. **End-to-end workflows** — Define 5 realistic multi-step tasks
5. **Variant A/B testing** — Swap descriptions and measure deltas
6. **Regression tracking** — Add git_sha + nightly CI integration

### Phase 3 (Medium Impact, High Effort)
7. **Cross-tool composition** — Chained task tests ✅ (`evals/composition_test.py`)
8. **Performance profiling** — Per-tool latency breakdown ✅ (`evals/profiler.py`)
9. **Instruction staleness** — Static + runtime docstring verification ✅ (`evals/instruction_staleness.py`)
10. **Toolset transition costs** — Context-switch measurements ✅ (`evals/transition_test.py`)

---

## Immediate Next Steps

1. Implement real LLM eval loop with qwen-coder:30b
2. Add token tracking to OllamaAgent
3. Run variant A/B test: baseline vs post-PR descriptions
4. Log everything to MLFlow with variant + git_sha tags

**Expected Outcome**: Quantified proof that PR #133-#136 actually improved agent accuracy (or didn't, which is also valuable data).
