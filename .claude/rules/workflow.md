---
paths:
  - "**/*"
---

# Workflow Pipeline (canonical)

Applies to every change in godot-mcp — a one-line fix and a multi-issue feature follow the same order, only the size of each step varies. The roadmap is issue-driven (`gh issue list`); the issue is the unit of merge.

If you skip a step, name which one and why, in the same turn.

```
1. Issue exists      →  GitHub issue tracking the work (one issue per merge)
2. Failing test      →  Red test pinning the behavior or reproducing the bug
3. Green code        →  Minimal change that turns it green
4. Preflight clean   →  tests / type / lint / zero-skips all green
5. PR opened         →  Branch pushed, PR references the issue (closes #N)
6. Comments addressed →  Every review comment resolved or replied to
7. Merge             →  Only after preflight green AND comments resolved
```

Each step gates the next.

## The steps

1. **Issue exists.** Every merge to `main` traces to an issue. Find a defect or refactor target mid-task? Open an issue first — don't bury it in an unrelated PR.
2. **Failing test (per [[testing]]).** Write it first; confirm it fails for the right reason before writing code. For `[Both]` issues the test usually pins the bridge envelope against a fake peer. Commit test + fix together.
3. **Green code.** Minimum to pass. Refactor in a separate step once green is locked.
4. **Preflight clean.** Server touched: `pytest` (contract + unit at least), type check, lint, zero-skip scan. Addon touched: load the plugin in Godot 4.4+ and confirm it enables/disables without errors.
5. **PR opened.** Title `<type>(<scope>): <summary> (closes #N)`; body has a summary, the issue's acceptance criteria as a checklist, and a Test plan. For a change **significant to the knowledge graph** (new tool/handler/model/module, moved/renamed files, or an architectural shift), refresh the graph first — `scripts/graphify.sh update . && scripts/graphify.sh label .` — and glance at `graphify-out/GRAPH_REPORT.md` for drift (a new god-node, an `mcp_server`↔addon edge bypassing the bridge, safety leaking into the addon); see [[graphify]]. Skip for one-line / doc / test-only changes — `graphify-out/` is gitignored, so it's a pre-PR sanity pass, not a commit.
6. **Comments addressed.** The automated reviewer is the **Qodo / The-PR-Agent** bot (`k3s-qodo-pr-agent`, configured in `.pr_agent.toml`, running open-source models on Ollama Cloud). It auto-runs `/describe` + `/review` on open; `/improve` is manual. **Wait for its review to land before addressing anything** — don't pre-emptively self-review. Treat findings as **advisory**: fix real issues, reply to misreads. Every comment gets a code change or a written reply; a separate concern → a follow-up issue, linked.
7. **Merge.** CI green, preflight green, Qodo review addressed. Squash; delete branch.

## Anti-patterns

- Tests written after implementation; bug fixes with no regression test.
- "I'll open the issue later." Bundling unrelated drive-by fixes into a feature PR.
- Pushing a failing test "to get CI to run it."
- Resolving a review comment with neither a change nor a reply.

State, in one line, which step you are on and the evidence the previous step is done.
