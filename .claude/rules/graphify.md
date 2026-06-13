---
paths:
  - ".env"
  - ".graphifyignore"
  - "graphify-out/**"
  - "scripts/graphify*"
---

# Graphify (LLM extraction policy)

The project's knowledge graph (`graphify-out/`) is built with the **graphify** CLI
running against a **local ollama** backend. The backend, model, and tuning are
configured in the repo-root `.env` (gitignored), not on the command line:

```
OLLAMA_BASE_URL=http://localhost:11434/v1   # presence → ollama is auto-detected
OLLAMA_MODEL=...                            # overrides graphify's default model
OLLAMA_API_KEY=ollama
GRAPHIFY_OLLAMA_KEEP_ALIVE=30m
GRAPHIFY_API_TIMEOUT=600
```

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
spawned by tooling don't auto-source it. Without these vars:

- `detect_backend()` returns `None` (no API key resolves) — no LLM backend, so
  community labeling falls back to `Community N` placeholders.
- the ollama default model is `qwen2.5-coder:7b`, which is **not installed** here
  — any LLM step errors out.

Sourcing `.env` makes auto-detect resolve to `ollama` with `OLLAMA_MODEL`, so no
`--backend`/`--model` flags are needed. The `/graphify` *skill* flow is separate:
it dispatches Claude subagents (or Gemini), not ollama — ollama applies only to
the `graphify` CLI covered by this rule.

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

## Maintenance

- After any `graphify` upgrade/reinstall, re-run `scripts/graphify_gdscript_support.py`
  with the pinned interpreter — the site-packages `.gd` patch is wiped on reinstall.
- `.graphifyignore` keeps the graph focused on the MCP itself (server + addon + docs);
  flip a line to `!` to re-include an excluded tree.
