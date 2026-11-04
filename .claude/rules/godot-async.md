---
read_when: "Writing deferred, threaded, or long-running work in Godot"
---

# Godot Async: Never Block the Main Thread

The engine and editor run on one main thread. Slow work is deferred,
chunked across frames, or moved to a worker with an explicit hand-back.

## MUST

- No blocking work on the main thread: no `OS.delay_msec`, tight loops,
  synchronous network waits, or large synchronous IO.
- Worker threads never touch the scene tree; they hand results back with
  `call_deferred`.
- Awaiting a signal that may never fire has a timeout.
- A worker task does not outlive the object or frame budget that owns it;
  cancel it on `_exit_tree`.
- Failures from async work are returned or emitted, not only `push_error`ed.

## SHOULD

- Chunk large operations across frames (`await get_tree().process_frame`).
- One in-flight operation per target; reject or queue a second.

## ANTI-PATTERNS

- `while true` without a frame yield.
- Unawaited coroutines that outlive their node.
- Treating a timeout as success.
