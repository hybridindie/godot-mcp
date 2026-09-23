---
type: index
title: "The readiness envelope"
description: "Why poll-based tools self-report pending reasons, the token table, and the no-silent-stall rule."
created: 2026-09-19
updated: 2026-09-23
---

# The readiness envelope

Some handlers cannot complete on the first call: an editor screenshot needs a
rendered frame, a property monitor needs the probe's next sample batch, a
full-Control UI scan takes a frame or two. The naive design — the handler
blocks until the data exists — stalls the bridge, blocks the editor's main
thread, or times out with a generic error pointing at the wrong layer.

Instead, poll-and-cache handlers **always answer within one round-trip**:

```jsonc
// not yet — and here is why
{ "ready": false, "pending": true, "reason": "capture_pending" }
// ready
{ "ready": true, "samples": [...] }
```

## The token table

| Token | Handler | Meaning |
|-------|---------|---------|
| `recording_pending` | `godot_input_stop_recording` | the stop push hasn't landed from the probe yet |
| `capture_pending` | `godot_runtime_get_property_samples`, game-frame capture | the request is dispatched; the probe answers on a later frame |
| `scan_in_flight` | `godot_runtime_find_ui_elements` | the full-Control scan runs over the next frames |
| `probe_pending` | `godot_profiling_get_performance_monitors` | the probe hasn't answered the first monitor pull |
| `rescan_in_flight` | `godot_asset_import_get_status` | the editor's filesystem scan is running; the status read is provisional |

`godot_asset_import_get_status` also reports `scanning: bool` — the same
`EditorFileSystem.is_scanning()` read the parse-check gate keys on, so an agent
can distinguish "not imported yet" from "the scan hasn't flushed".

## `poll_ready` and the no-silent-stall rule

The server-side loop is `poll_ready(bridge, command, params, timeout_ms)`:

1. Make at least one attempt (a fast tool never returns a pending answer).
2. Poll on a fixed cadence until the result is `ready` or the deadline hits.
3. On expiry: if the last result carried a `reason`, the tool raises a
   `TIMEOUT` error **relaying it** — the agent sees
   `TIMEOUT: … did not become ready within 2000ms (last reason:
   capture_pending)` and can act on the cause instead of guessing.

The design rule: **no bridge call can stall silently, and every `ready: false`
beyond a grace period names its cause.** A handler that can't complete should
never hang the transport; the addon is the only layer that knows *why* Godot
isn't cooperating, so it says so.

## Grace periods

Not every first-poll miss is a failure — captures legitimately defer by a
frame. So the pattern is:

- **Captures** (screenshots, frames): 2 polls (one frame deferral + slack).
- **Probe-based polls**: the standard poll cadence
  (`DEFAULT_POLL_INTERVAL_SECONDS`), bounded by the tool's `timeout_ms`.

A handler may defer normally (one empty `ready: false`); only a *still-pending*
handler past its grace window carries the token. In practice every handler
listed above emits the token on every non-progress poll — simpler to reason
about, and `poll_ready`'s deadline is the real bound.

## Why agents care

Without the token, a pending poll and a broken probe are indistinguishable —
the agent burns its retry budget on a capture that will never land, or gives up
on one that needs one more frame. With it:

- `recording_pending` → the game is still flushing the input buffer; wait, or
  check `input_get_stats`.
- `scan_in_flight` → the UI scan is running; poll once more.
- `probe_pending` → the probe autoload is present but slow; check
  `runtime_is_playing`.
- `rescan_in_flight` → the import is *progressing*; keep polling rather than
  re-importing.