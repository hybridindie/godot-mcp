# Evaluation Framework for godot-mcp

Real LLM agent evaluation suite for the godot-mcp bridge. Tests multi-dimensional agent
behavior (tool choice, prerequisites, recovery, efficiency) across a 28-task suite that
exercises a representative slice of the full tool surface.
Supports both local (Ollama) and cloud (Claude/GPT/Gemini) LLMs for comparison matrices.
Results are reported to the console; MLflow logging lives in **godot-agents** (see below).

## Files

| File | Purpose |
|------|---------|
| `evals/llm_eval_v2.py` | Main 28-task expanded evaluation suite. Filters tools per task, runs isolated cleanup, scores multi-dimensionally. |
| `evals/agent_suite_v2.py` | Core agent framework: `BridgeConnector`, `TaskScore`, task definitions, `run_task`. |
| `evals/ollama_agent.py` | Ollama local LLM integration (qwen3-coder:30b). Token tracking, latency capture, JSON parsing. |
| `evals/cloud_client.py` | Cloud LLM integration — Anthropic Claude, OpenAI GPT, Google Gemini. Drop-in replacement for OllamaAgent. |
| `evals/profiler.py` | Per-tool latency aggregator (mean/median/p95/error-rate). |
| `evals/variant_ab_test.py` | A/B testing framework for tool description variants. |
| `evals/composition_test.py` | Cross-tool composition chains with param resolution. |
| `evals/negative_test.py` | Safety/error boundary tests. |
| `evals/batch_perf_test.py` | Performance regression test for batch operations. |
| `evals/instruction_staleness.py` | Static + runtime tool staleness detector. |
| `evals/transition_test.py` | Toolset context-switch cost measurement. |
| `evals/README.md` | This file. |

## Quick Start

### Run the full 28-task suite (local Ollama)
```bash
python -m evals.llm_eval_v2
```

### Run a subset of tasks
```bash
python -m evals.llm_eval_v2 --tasks inspect_scene_tree script_write_and_read
```

### Run with a cloud model (requires API key)
```bash
export ANTHROPIC_API_KEY=sk-ant-...
python -m evals.llm_eval_v2 --model claude-sonnet-4 --provider anthropic

export OPENAI_API_KEY=sk-...
python -m evals.llm_eval_v2 --model gpt-4o --provider openai

export GOOGLE_API_KEY=...
python -m evals.llm_eval_v2 --model gemini-2.5-pro --provider google
```

### Run Phase 2 tools
```bash
# A/B variant testing
python -m evals.variant_ab_test --variants baseline agent_optimized

# Composition chains
python -m evals.composition_test

# Negative/safety tests
python -m evals.negative_test

# Performance profiling
python -m evals.profiler
```

### Run Phase 3 tools
```bash
# Instruction staleness (static + runtime)
python -m evals.instruction_staleness --all

# Toolset transition costs
python -m evals.transition_test --model qwen3-coder:30b
```

## Reported metrics

The suites print these per-run (no external tracker):

- `completion_rate` — % of tasks scoring ≥0.7
- `mean_score` — weighted overall score (0.0-1.0)
- `first_attempt_rate` — % correct on first tool call
- `mean_steps` — average tool calls per task
- `mean_errors` — average errors per task
- `mean_duration_ms` — average wall-clock time per task
- `token_efficiency` — tokens per step (lower is better)
- Per-task breakdowns: `{task_name}_success`, `{task_name}_steps`, etc.
- Per-tool latency: mean/median/p95/error-rate

## MLflow moved to godot-agents

The `mlflow` Python package conflicts with the pinned FastMCP 4.x, so it is **not a godot-mcp
dependency** (removed 2026-08). Eval→MLflow logging — the tracker, the GenAI dataset sync, and
the `mlflow` MCP server — is owned by **godot-agents** (the shared `Godot AI` experiment,
`https://mlflow.johndstudios.net`). godot-mcp evals stop at console output; if you need run
telemetry, have godot-agents drive the evals and log there.

## Model Comparison Matrix

| Dimension | qwen3-coder:30b | gemma4:12b-mlx | claude-sonnet-4 | gpt-4o |
|-----------|-----------------|----------------|-----------------|--------|
| **Mean score** | 0.86 | — | — | — |
| **Compliance** | 75% | 20% | — | — |
| **First-attempt** | 71% | — | — | — |
| **Mean steps/task** | 5.0 | — | — | — |
| **Tokens/task** | 2,610 | — | — | — |
| **Latency/call** | 92ms | 6.8ms | — | — |

> Cloud model slots (—) are filled by running:
> ```bash
> python -m evals.llm_eval_v2 --provider anthropic --model claude-sonnet-4
> ```

## MLFlow Instance

Tracking URI: `https://mlflow.johndstudios.net`
Experiment: `Godot AI` (the unified experiment shared with the godot-agents project; consolidated 2026-06-16)

## Current Limitations

1. **Debugger evals require manual pause**: The harness can't reliably pause the running game via `force_break` or `set_breakpoint` in headless mode. For accurate debugger tool evals, pause the game manually (via editor breakpoint or the DebuggerDemo's `breakpoint` keyword) before running the harness.

2. **Cloud model costs**: Running the full 28-task suite against Claude/GPT costs ~$2-5 in API tokens. Use `--tasks` to run a subset for quick validation.

## Representativeness — addon-direct vs. server-mediated (#197)

The LLM eval agents here (`OllamaAgent`, `CloudAgent`) execute tool calls by sending `cmd_*` envelopes **straight to the addon bridge** (`CloudAgent._execute`), bypassing the FastMCP server's safety classes, preconditions, `dry_run`/`confirm`, the approval webhook, and toolset gating. So their results do **not** reflect the safety behaviour a real, *server-mediated* client (e.g. [godot-agents](https://github.com/hybridindie/godot-agents), which already goes through the server) experiences — PRD FR3 wants the agent-representative path to run through the server.

**Decision:** rather than migrate the execution path now (which means standing up an MCP client/session and switching from addon `cmd_*` param keys to the server tool surface), every `run_llm_suite` run is **explicitly labelled non-representative** until that migration lands: a console banner (`REPRESENTATIVENESS_BANNER`, `evals/llm_eval_v2.py`) prefixes every suite run. The former MLflow run-params label moved to godot-agents with the MLflow decoupling (#378). When the agent is routed through the server, drop the banner.

## Results Archive

Historical reports and ad-hoc test logs are in `evals/results/archive/`.
Key reports in `evals/results/`:
- `gap_analysis.md` — complete gap analysis (all 10 vectors implemented)
- `phase2_report_2026-06-10.md` — Phase 2 evaluation report
- `expanded_llm_eval_report_2026-06-10.md` — 28-task expanded eval report
- `post_improvement_eval_2026-06-10.md` — eval after prompt engineering fixes
- `partial_tasks_analysis_2026-06-11.md` — analysis of 7 partial tasks

## Legacy Files

Pre-v2 eval artifacts are archived in `evals/archive/`:
- `agent_suite.py`, `suite.py`, `llm_eval.py`, `runner.py`, `harness.py`, `variants.py`
