---
title: Safety classes
description: The class model, dry_run/confirm semantics, and the class × tool matrix rules.
---

# Safety classes

Every tool carries exactly one safety class in `meta.safety_class`, and the
class determines the required parameters. The authoritative rule text lives in
[`.opencode/rules/mcp-tools.md`](https://github.com/hybridindie/godot-mcp/blob/main/.opencode/rules/mcp-tools.md);
the machine-checked matrix is [`docs/tool-contracts.md`](https://github.com/hybridindie/godot-mcp/blob/main/docs/tool-contracts.md).

## The model

| Class | Risk | Extra params | UndoRedo |
|-------|------|--------------|----------|
| `read_only` | Never mutates | none | n/a |
| `mutating` | Reversible editor change | `dry_run: bool = False` | wrapped |
| `destructive` | Deletes/overwrites; maybe irreversible | `dry_run` **and** `confirm: bool = True` | wrapped (captures prior state) |
| `runtime` | Controls game execution | varies | varies |

## `dry_run`

Runs preconditions and returns what *would* happen. Key properties:

- Nothing is sent to the editor (asserted by contract tests — `"cmd_…"` absent
  from the bridge traffic).
- The preview carries the **same persistence verdict** the real run will stamp
  (the `cmd_node_persistence` probe runs the identical rule).
- Batch previews report the projected `undoable` flag.
- A dry-run must never be a containment bypass: the same server-side path
  containment (`res://`-only) applies to the preview's existence probe.

## `confirm`

Required for every destructive tool, without exception. The refusal is a
structured precondition, so an agent can react:

```jsonc
{ "error": "PRECONDITION_FAILED",
  "hint": "This call discards unsaved changes. Set confirm=True to proceed.",
  "required": "confirm" }
```

The recommended flow: `dry_run=true` first (read what will be affected), then
`confirm=true` when the preview is acceptable. Destructive tools that remove
state capture that state for undo (e.g. `remove_audio_bus` restores the whole
bus + effects on undo; `delete_resource_file` restores exact bytes).

## Where the classes come from

The class is metadata on the tool registration; `mcp_server/safety.py` owns
`MUTATING` / `READ_ONLY` / `DESTRUCTIVE` / `RUNTIME` constants and the
`enforce_preconditions` decorator that checks them. The addon never decides
whether an action is allowed — it honors the flags defensively (e.g. the
add-on-side `confirm` check on `cmd_delete_node`).

## The matrix rules

The full class × tool matrix is machine-checked (`docs/tool-contracts.md` +
tests). Invariants:

- No mutating/destructive tool lacks `dry_run`.
- No destructive tool lacks `confirm`.
- No tool merges classes (delete is never folded into a fat "node" tool — the
  gate would be buried).
- Read-only tools never mutate — a `read_only` tool that writes is a bug the
  contract tests catch.

## `godot_undo`

Every UndoRedo-wrapped mutation is reversible by the human's own undo stack;
`godot_undo` (always-on `core`) steps back one action. The documented
exception: batch sets above 20 nodes bypass the stack for performance — and
the result says so via `undoable: false`.