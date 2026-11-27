<!--
  context-discovery.md — Shared greenfield/brownfield discovery probe
  Referenced by: epic-composer, task-decomposer
  version: 1.1.1, owner: John D
  Single source of truth for the greenfield/brownfield detection previously
  duplicated across skills.
-->

# Context Discovery

Before synthesizing source material or decomposing work, determine whether
the project is greenfield or brownfield. The classification changes which
constraints are available.

## Classification

- If the workspace has existing code (source files, package manifests, README,
  AGENTS.md), classify as **brownfield**.
- If the workspace is empty or only has config files, classify as
  **greenfield**.

## Brownfield probes

If brownfield, read the following (where present) and record findings as
**Project Constraints**:

- `AGENTS.md` or `README.md` — conventions, architectural rules.
- Package manifest (`package.json`, `pyproject.toml`, `go.mod`, etc.) — tech
  stack and dependencies.
- Existing test files (glob) — testing conventions.
- Existing code structure — architectural constraints, patterns, and
  conventions; name the specific files, modules, and components the work will
  touch.

## Greenfield handling

If greenfield:
- Note that there are no existing constraints from the codebase.
- Rely entirely on user-provided material for constraints.
- When naming new files, components, or APIs, mark them as "(new)".

## How callers use this file

- `epic-composer` runs this before shaping the outcome and records the
  findings as constraints.
- `task-decomposer` uses it to name real files and components (brownfield) or
  mark new ones "(new)" (greenfield).