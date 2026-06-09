# Debugger Feasibility Report (issue #110)

**Status:** Research spike (no merged tools)
**Godot version tested:** 4.4+ (stable protocol)
**Deliverable date:** 2026-06-09

## Summary

**RECOMMENDATION: GO.** The Godot editor→game debugger protocol supports step control, stack-frame inspection, and expression evaluation over the same `EditorDebuggerSession.send_message()` mechanism already used for Tier 1 breakpoints.  Async replies are captured via the existing poll-and-cache pattern (`EditorDebuggerPlugin._capture()`), reusing the `#66` runtime-probe infrastructure.

A Tier 2 debugger toolset (`step_*`, `continue`, `get_stack_frames`, `evaluate_expression`) is implementable with **no engine changes**.

## What we already know

### Tier 1 (shipped in PR that resolved #110)

| Tool | Protocol message | Addon-side implementation |
|------|-----------------|--------------------------|
| `set_breakpoint` | `session.set_breakpoint(path, line, true)` | `EditorDebuggerSession.set_breakpoint` (direct API) |
| `remove_breakpoint` | `session.set_breakpoint(path, line, false)` | Direct API |
| `clear_breakpoints` | `session.set_breakpoint(..., false)` per tracked + probe message | Iterative + probe message |
| `force_break` | `debugger.send_to_probe("godot_mcp:force_break", [])` | `EngineDebugger.debug(true)` in probe |

### Key signals

`EditorDebuggerSession` emits useful session state:
- **`breaked(can_debug)`** — fired when the remote game enters the debug loop (i.e. at a breakpoint or after `force_break`).
- **`continued()`** — fired when the game resumes.
- **`started()`** / **`stopped()`** — session lifecycle.

`is_breaked()` returns whether the game is currently paused.

---

## Research questions & findings

### Q1: Can we step? (step_over / step_into / step_out)

**YES.** The `RemoteDebugger` (`core/debugger/remote_debugger.cpp`) inside the running game handles these protocol messages during the debug loop:

```cpp
// From core/debugger/remote_debugger.cpp (Godot 4.x source)
if (command == "step") {
    script_debugger->set_depth(-1);
    script_debugger->set_lines_left(1);
    break;
} else if (command == "next") {
    script_debugger->set_depth(0);    // same depth
    script_debugger->set_lines_left(1);
    break;
} else if (command == "out") {
    script_debugger->set_depth(1);    // caller depth
    script_debugger->set_lines_left(1);
    break;
}
```

Send via `EditorDebuggerSession.send_message("step", [])` from the editor.
The game breaks out of the debug loop and resumes until it hits the next line.

### Q2: Can we read the stack?

**YES.** Sending `"get_stack_dump"` returns a `ScriptStackDump` object serialized into a protocol array. The game sends back `"stack_dump"` with frames containing:
- `file` (res:// path)
- `line` (int)
- `func` (function name)

Our addon's `EditorDebuggerPlugin._capture()` would intercept `"stack_dump"` and cache it,
just like `#66` caches `"godot_mcp:scene_tree"`.

### Q3: Can we evaluate expressions?

**YES.** Sending `"evaluate"` with `[expression, frame]` returns `"evaluation_return"` carrying:
- `name` (the original expression)
- `value` (Variant serialized)

Godot's `RemoteDebugger::debug()` implementation parses the expression via `Expression.parse()`,
binds locals/globals/ClassDB singletons, and executes against the current stack-level instance.

### Q4: Can we read frame variables (locals, members, globals)?

**YES.** `"get_stack_frame_vars"` with `[frame]` triggers the game to send:
- `"stack_frame_vars"` (total count)
- Multiple `"stack_frame_var"` messages for each local, member, and global variable
  (type: 0=local, 1=member, 2=global)

The game code:
```cpp
script_lang->debug_get_stack_level_locals(lv, &locals, &local_vals);
script_lang->debug_get_stack_level_members(lv, &members, &member_vals);
script_lang->debug_get_stack_level_globals(&globals, &globals_vals);
```

---

## Architecture for a Tier 2 toolset

### Proposed tools

All `runtime` class (like Tier 1), gated in the existing `debugger` toolset.

| Tool | Params | Returns |
|------|--------|---------|
| `step_into` | — | `StepResult { hit, paused }` |
| `step_over` | — | `StepResult { hit, paused }` |
| `step_out` | — | `StepResult { hit, paused }` |
| `continue_execution` | — | `ContinueResult { running }` |
| `get_stack_frames` | — | `StackFramesResult { frames[]{file, line, func} }` |
| `evaluate_expression` | `expression, frame=0` | `EvaluationResult { expression, value }` |
| `get_frame_variables` | `frame=0` | `FrameVarsResult { locals[], members[], globals[] }` |

### Precondition

Every tool enforces the game is in a break state:

```gdscript
if not session.is_breaked():
    return {"ok": false, "error": "PRECONDITION_FAILED",
            "hint": "The game is not paused. Set a breakpoint or force_break and trigger it first.",
            "required": "break_state"}
```

### Async pattern (same as #66)

1. `get_stack_frames` calls `session.send_message("get_stack_dump", [])`.
2. Game replies via debugger protocol → `_capture("stack_dump", data, session_id)` fires.
3. Cache the parsed frames in `MCPDebugger._stack_frames`.
4. Server-side tool polls `get_stack_frames` until `ready=true` or timeout.

The MCP-side implementation mirrors `get_game_scene_tree` / `get_property_samples` exactly.

### Expression evaluation caveat

The evaluator in the game requires a **valid script instance** at the target frame. If the function is static or the instance was freed, `_capture` would never receive `"evaluation_return"` (or it sends a null/error). The tool should surface this as:

```gdscript
{"ok": false, "error": "EVALUATION_ERROR",
 "hint": "Expression could not be evaluated. The frame may be static or the instance freed."}
```

---

## Fallback: Log-point debugging

If the protocol approach fails (or as an alternative when no play session is active), log-point debugging is always available:

1. Inject `print("VAR_NAME = ", some_var)` at a specific line via `patch_script`.
2. `run_and_capture` executes the scene.
3. Parse stdout for the logged value.
4. Patch the script back to remove the print statement.

This is **slow and intrusive** but works with no editor debug session at all.
Recommendation: document the fallback but don't build a dedicated toolset for it.

---

## Go / No-go

| Capability | Status | Notes |
|-----------|--------|-------|
| Step over | **GO** | Stable protocol since 4.0 |
| Step into | **GO** | Stable protocol since 4.0 |
| Step out | **GO** | Stable protocol since 4.0 |
| Continue | **GO** | Stable protocol |
| Stack dump | **GO** | Requires poll-and-cache pattern |
| Frame variables | **GO** | Requires poll-and-cache pattern |
| Expression eval | **GO** | Limited by frame context |
| Watch variables | **PARTIAL** | Manual re-poll no auto-refresh |
| Conditional breakpoints | **DEFERRED** | Needs protocol protocol extensions |
| Async/multi-threaded stacks | **NO** | Only main thread debugged |

---

## Next steps (implementation issue)

Create a follow-up issue for Tier 2 debugger tools with acceptance criteria:

- [ ] Extend `MCPDebugger` with `_stack_frames`, `_evaluation_result`, `_frame_vars` caches
- [ ] Implement `cmd_step_into`, `cmd_step_over`, `cmd_step_out`, `cmd_continue_execution`
- [ ] Implement `cmd_get_stack_frames`, `cmd_evaluate_expression`, `cmd_get_frame_variables`
- [ ] Server-side tools in `mcp_server/tools/debugger.py`
- [ ] Models for `StepResult`, `StackFramesResult`, `EvaluationResult`, `FrameVarsResult`
- [ ] Contract + integration tests
- [ ] Update `docs/tool-contracts.md`
- [ ] Zero skipped tests

## References

- `core/debugger/remote_debugger.cpp` — Godot source for debug-loop command handling
- `modules/gdscript/gdscript_editor.cpp` — `debug_get_stack_level_*` / `debug_parse_stack_level_expression`
- `EditorDebuggerSession` — `send_message()`, `set_breakpoint()`, `is_breaked()`, `breaked`/`continued` signals
- Existing `#66` runtime-probe infrastructure — poll-and-cache pattern
- Existing `#110` Tier 1 breakpoint infrastructure — `session.set_breakpoint()` + `_capture()`
