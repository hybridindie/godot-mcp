# Evals (server self-analysis only)

`evals/` holds **one** thing in this repo: the Instruction Staleness Verifier —
static analysis of godot-mcp's *own* tool docs vs. the addon's bridge handler
registrations. It is server self-analysis, not an agent evaluation.

The LLM eval **harness** (agents, task suites, variant A/B testing, transition/
composition/negative/batch runners, results archives) is a consumer concern and
lives in **godot-agents** as the self-contained `godot_agent_harness` package
(godot-agents#481, moved in #383). It imports `godot_editor_mcp` only via the
published wheel — no cross-repo source imports.

## Usage

```bash
# Static analysis: bridge.send()/route() cmd_* vs addon handlers["cmd_*"] + doc drift
uv run python -m evals.instruction_staleness --static

# Runtime verification: call each shared cmd_* through the bridge
uv run python -m evals.instruction_staleness --runtime

# Both
uv run python -m evals.instruction_staleness --all
```

## Why the harness moved

- godot-mcp is **game-agnostic and consumer-independent**; the harness evaluated
  *agents* (OllamaAgent, CloudAgent, LangGraph-side consumers), not the server.
- godot-agents owns the eval agents, telemetry, and the unified "Godot AI"
  experiment; vendoring the harness there (with the #276 bridge topology fix —
  `serve()` + addon-dials) keeps this repo's surface generic.
- Server-side safety gates (`confirm`, `dry_run`, toolset gating) are exercised
  by `tests/contract/` here, not by LLM-run trials.