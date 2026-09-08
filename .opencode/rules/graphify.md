---
paths:
  - ".env"
  - ".graphifyignore"
  - "graphify-out/**"
  - "scripts/graphify*"
---

# Graphify (LLM extraction policy)

The project's knowledge graph (`graphify-out/`) is built with the **graphify**
CLI. The LLM backend, model, and tuning live in the repo-root `.env`
(gitignored), not on the command line.

**Policy: LOCAL OLLAMA ONLY — no cloud models.** graphify's `detect_backend()`
checks cloud keys (gemini → kimi → claude → openai → deepseek) **before**
`ollama`, so the only safe configuration is the one this repo pins: no cloud
API keys in `.env` (or the environment), ollama vars set. `.env` must never
contain `OPENAI_*`, `ANTHROPIC_*`, `GEMINI_*`, `KIMI_*`, or `DEEPSEEK_*` keys:

```
# Local ollama (OpenAI-compatible endpoint on localhost:11434)
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2.5-coder:7b   # any model pulled with `ollama pull`
OLLAMA_API_KEY=ollama           # any non-empty value; silences the F-029 warning
GRAPHIFY_OLLAMA_KEEP_ALIVE=30m
```

If a cloud key appears in the ambient environment, do not let auto-detect pick
it up — run with an explicit `--backend ollama` or unset the key first.

## The rule: always observe `.env` when running graphify

**Never invoke `graphify` (or `python -m graphify`) directly. Run it through
`scripts/graphify.sh`**, which sources `.env` and uses the pinned interpreter
(`graphify-out/.graphify_python`):

```bash
scripts/graphify.sh label . --update
scripts/graphify.sh query "How does the bridge work?"
```

If you must call graphify by hand, source `.env` into the environment first:

```bash
set -a; . ./.env; set +a
$(cat graphify-out/.graphify_python) -m graphify <args>
```

## Why this matters

graphify reads `os.environ` but **does not load `.env` itself**, and shells
spawned by tooling don't auto-source it. Without these vars `detect_backend()`
returns `None` — no LLM backend, so community labeling falls back to
`Community N` placeholders and any extraction/label step errors out.

Sourcing `.env` makes auto-detect resolve to `ollama` (no cloud keys are set;
if one ever leaks into the environment, pass `--backend ollama` explicitly).
The `/graphify` *skill* flow is separate: it dispatches Claude subagents (or
Gemini), not the gateway — the CLI backend in this rule covers
`scripts/graphify.sh` only.

## Auto-refresh on commit (git hooks)

Tracked git hooks keep the graph **structure** in sync with the code. After a
commit or merge that touches `mcp_server/**/*.py` or `godot/addons/godot_mcp/**/*.gd`,
`scripts/hooks/{post-commit,post-merge}` run `scripts/graphify.sh update .` —
AST-only, **LLM-free** (~1-2s), and `graphify-out/` is gitignored so there's no
commit churn. They no-op when no graph-relevant source changed.

Activate once per clone (sets the per-checkout `core.hooksPath`):

```bash
scripts/hooks/install.sh
```

`update` re-clusters, which resets community **labels** to `Community N`
placeholders. Names are cosmetic for `query`/`explain` (which traverse nodes/edges);
refresh them on demand — or on a cadence — with `scripts/graphify.sh label .`.

## Refresh the graph before a significant PR

The commit hooks keep the graph **structure** current (AST, free) but reset
community **labels** on every re-cluster. Before opening a PR whose change is
**significant to the graph** — a new tool / handler / model / module, a moved or
renamed file, or an architectural shift (a new god-node, a new cross-layer edge) —
refresh the map so it's accurate for reviewers and the `query`/`explain` flows,
then read it as a lightweight architecture self-review:

```bash
scripts/graphify.sh update .    # structure reflects the branch (free, AST-only)
scripts/graphify.sh label .     # regenerate community names via local ollama
```

Then glance at `graphify-out/GRAPH_REPORT.md` — **God Nodes** + **Surprising
Connections** make architectural drift visible: a safety helper leaking into the
addon, a direct `mcp_server`↔addon edge that bypasses the bridge seam, a mutating
tool that no longer routes through `run_or_preview`, or an unexpected new
god-node. Fold anything surprising into the PR description or a follow-up issue.

**Skip it** for a one-line fix, a doc/test-only change, or a rename with no new
symbols. `graphify-out/` is gitignored, so this is a pre-PR sanity pass — it never
adds commit churn.

## Maintenance

- The `openai` package must be present in graphify's tool env (it is imported
  lazily for the ollama OpenAI-compatible client). If a run errors with
  `No module named 'openai'`, reinstall with:
  `uv tool install graphifyy --with mcp --with openai --force`.

- After any `graphify` upgrade/reinstall, re-run `scripts/graphify_gdscript_support.py`
  with the pinned interpreter — the site-packages `.gd` patch is wiped on reinstall.
- `.graphifyignore` keeps the graph focused on the MCP itself (server + addon + docs);
  flip a line to `!` to re-include an excluded tree.
