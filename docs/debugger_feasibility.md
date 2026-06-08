# Debugger Feasibility Spike: GDScript Breakpoint/Step/Stack/Eval

> **Issue**: [#110](https://github.com/hybridindie/godot-mcp/issues/110)  
> **Date**: 2026-06-08  
> **Status**: Research in Progress  
> **Goal**: Determine go/no-go for true debugger integration vs. fallback log-point debugging.

---

## 1. Executive Summary

This document captures findings from researching Godot 4.x's debugger APIs for breakpoint control, single-stepping, stack-frame inspection, and expression evaluation — the largest capability gap vs. Nwiro Pro's BP Debugger.

**Initial Verdict: GO — with hybrid architecture.**

Godot exposes enough debugger API surface for a functional implementation, but not all features are available through clean GDScript methods. A **hybrid approach** is recommended:
- **Editor side**: Use `EditorDebuggerSession.set_breakpoint()` for breakpoint injection.
- **Game side (probe)**: Use `EngineDebugger.debug()` for forced breaks and message capture for stack/eval.
- **Protocol messages**: Required for `step_over`, `step_into`, `continue`.

---

## 2. What Nwiro Pro's BP Debugger Does

Nwiro provides ~10 debugger tools:
- `set_breakpoint` / `remove_breakpoint`
- `step_over` / `step_into`
- `continue_execution`
- `get_stack_frames` (file, line, function, local variables)
- `evaluate_expression` (arbitrary GDScript expressions in stack context)
- `watch_variable`
- `compile_error_analysis` + `auto_fix`

---

## 3. Godot Debugger Architecture Refresher

Godot's debugger is a **message-based protocol** between editor and game:

```
Editor (EditorDebuggerPlugin + EditorDebuggerSession)
    ↕ custom message channel (e.g., "godot_mcp:")
Game (EngineDebugger + runtime probe autoload)
```

The editor's built-in **Script Debugger** tab uses the same protocol but with a different prefix. Our `MCPDebugger` (`mcp_debugger.gd`) already captures the `godot_mcp:` prefix channel.

---

## 4. Research Findings

### 4.1 ✅ BREAKPOINT INJECTION — FEASIBLE

**Discovery**: `EditorDebuggerSession.set_breakpoint(path, line, enabled)` is documented in Godot docs.

```gdscript
# From EditorDebuggerPlugin context:
var session := get_session(session_id)
session.set_breakpoint("res://scripts/player.gd", 42, true)   # set
session.set_breakpoint("res://scripts/player.gd", 42, false)  # remove
```

**Also available on game side**:
```gdscript
# From runtime probe:
EngineDebugger.remove_breakpoint(source, line)
EngineDebugger.clear_breakpoints()
```

**Feasibility**: HIGH. The API is public, documented, and callable from GDScript.

### 4.2 ⚠️ SINGLE STEPPING — REQUIRES PROTOCOL MESSAGES

No documented GDScript methods for `step_over()`, `step_into()`, or `continue()` on `EditorDebuggerSession`.

**Hypothesis**: These are sent as raw protocol messages. The built-in Script debugger sends strings like:
- `"debugger_step"`
- `"debugger_next"` (step over)
- `"debugger_continue"`

**Research needed**: Inspect Godot C++ source for exact message strings:
- `editor/debugger/script_editor_debugger.cpp`
- `core/debugger/remote_debugger.cpp`

**Feasibility**: MEDIUM. If message names are stable across 4.4–4.6, we can `session.send_message("debugger_step", [])`. If they change per version, this becomes fragile.

### 4.3 ⚠️ STACK FRAME CAPTURE — REQUIRES GAME-SIDE COOPERATION

When the game hits a breakpoint, the editor receives a protocol message with stack frames. However, **custom `EditorDebuggerPlugin` only captures messages with its own prefix** (`godot_mcp:`).

**Options**:

#### Option A: Intercept built-in debugger messages
- Godot does **not** route built-in debugger messages to custom plugins.
- **Verdict**: NOT POSSIBLE without engine modification.

#### Option B: Game-side `breakpoint` keyword + probe reporting
- Inject `breakpoint` into source code → game pauses → probe detects pause? **No** — `breakpoint` pauses the game process, but the probe (a Node in the scene tree) also pauses; it cannot run `_process()` to send messages.

#### Option C: EngineDebugger state polling
- The game-side `EngineDebugger` may expose state we can poll. Research needed:
  - Does `EngineDebugger` have `is_breakpoint()` or `get_stack_frame()` methods?
  - Can the probe register a callback on breakpoint hit?

#### Option D: Hybrid — editor tracks breakpoints, game reports on continue
- Editor knows where breakpoints are set.
- When game pauses (detected via `is_playing_scene()` returning true but frozen), we infer a breakpoint was hit.
- But we don't know WHICH breakpoint or the stack frame...

**Feasibility**: LOW-MEDIUM for true stack frames. May need creative workaround.

### 4.4 ⚠️ EXPRESSION EVALUATION — PARTIALLY FEASIBLE

**Discovery**: `_debug_parse_stack_level_expression(level, expression, max_subitems, max_depth)` exists on `ScriptLanguageExtension`.

**Problem**: This is a method on `ScriptLanguageExtension`, not directly accessible from GDScript in a running game. It is used by the editor's built-in debugger.

**Alternative**: The game-side probe can use Godot's `Expression` class for basic math/logic, but **not** for evaluating variables in the current stack context. `Expression` has no access to local variables or `self` of the paused function.

**Feasibility**: LOW for true stack-context evaluation. MEDIUM for basic expression evaluation without stack context.

---

## 5. Proposed Hybrid Architecture

Given the findings, here's the recommended architecture that maximizes value while working within Godot's API constraints:

### 5.1 Editor Side (MCPDebugger addon)

**Breakpoint Management**:
```gdscript
# MCPDebugger extension
func set_script_breakpoint(path: String, line: int, enabled: bool) -> void:
    if _session_id >= 0:
        var session := get_session(_session_id)
        session.set_breakpoint(path, line, enabled)
```

**Step/Continue** (protocol messages — prototype needed):
```gdscript
func debugger_step() -> void:
    if _session_id >= 0:
        var session := get_session(_session_id)
        session.send_message("godot_mcp:step", [])  # or "debugger_step"
```

### 5.2 Game Side (mcp_runtime_probe.gd)

**Breakpoint Hit Reporting**:
```gdscript
# NEW in probe
func _capture(message: String, data: Array) -> bool:
    match message:
        # ... existing messages ...
        "breakpoint_hit":
            # Godot MIGHT send this when breakpoint is hit
            EngineDebugger.send_message("godot_mcp:breakpoint_hit", [{
                "file": data[0],
                "line": data[1],
            }])
            return true
```

**Forced Break**:
```gdscript
# NEW tool: cmd_force_break
func _force_break() -> void:
    EngineDebugger.debug(true, false)  # can_continue=true, is_error_breakpoint=false
```

### 5.3 Stack Frame Workaround

If native stack frame capture is impossible, implement a **cooperative stack trace**:

1. Agent requests stack trace.
2. Editor sends `godot_mcp:get_stack` to probe.
3. Probe uses `get_stack()` GDScript function (which returns the current call stack as an array of dictionaries in error handlers... wait, this is only available in `_get_stack()` which is internal).

Actually, GDScript has `get_stack()` which returns the current call stack — but only when called from within the running code. A probe sitting in `_process()` would only see its own stack, not the stack of the paused code.

**Alternative**: Inject `push_error("MCP_STACK_TRACE")` and capture the error through the debugger? The `EditorDebuggerPlugin` can capture errors via `_capture` with the error message format...

This is getting complex. Let me evaluate the fallback.

---

## 6. Fallback: Log-Point Debugging

If true debugger integration proves too limited, implement **log-point debugging** as a reliable fallback:

### 6.1 Mechanism

1. Agent requests "breakpoint" at `player.gd:42`.
2. Server reads `player.gd`, finds line 42, injects a log-point line before it:
   ```gdscript
   # Original line 42:
   velocity.y += gravity * delta
   
   # Injected log-point (line 42 becomes 43):
   push_warning("[MCP_LOGPOINT] player.gd:42 velocity=%s position=%s" % [velocity, position])
   velocity.y += gravity * delta
   ```
3. Server calls `play_scene()` → game runs.
4. When line is hit, `push_warning` appears in Output panel.
5. MCPDebugger can capture Output panel? **No** — we don't have Output panel API.

**Correction**: Use `run_and_capture` (headless subprocess) which captures stdout/stderr. But that doesn't use the editor play session...

**Better approach**: Use `EngineDebugger.send_message()` from the injected line:
```gdscript
EngineDebugger.send_message("godot_mcp:logpoint", [{
    "file": "res://scripts/player.gd",
    "line": 42,
    "locals": { "velocity": velocity, "position": position }
}])
```

But this requires modifying the source code to include `EngineDebugger` calls, which is heavy.

### 6.2 Simpler Log-Point

Inject `print()` statements, run via `run_and_capture` (headless), parse output:

```gdscript
# Injected:
print("[MCP_DEBUG] file=player.gd line=42 velocity=", velocity, " position=", position)
```

**Pros**: 100% reliable, no probe dependency, works in headless mode.
**Cons**: Not real-time (requires stop/re-run), pollutes source code (must clean up after).

---

## 7. Prototype Plan

To validate the hybrid architecture, we need two prototypes:

### Prototype A: True Debugger (editor side)

Create `godot/addons/godot_mcp/handlers/debugger.gd`:

```gdscript
@tool
class_name MCPDebuggerHandlers
extends RefCounted

var _router: MCPCommandRouter

func register(handlers: Dictionary) -> void:
    handlers["cmd_set_breakpoint"] = _cmd_set_breakpoint
    handlers["cmd_remove_breakpoint"] = _cmd_remove_breakpoint
    handlers["cmd_clear_breakpoints"] = _cmd_clear_breakpoints
    handlers["cmd_step_over"] = _cmd_step_over
    handlers["cmd_step_into"] = _cmd_step_into
    handlers["cmd_continue"] = _cmd_continue
    handlers["cmd_get_stack_frames"] = _cmd_get_stack_frames

func _cmd_set_breakpoint(params: Dictionary) -> Dictionary:
    var path := str(params.get("path", ""))
    var line := int(params.get("line", 0))
    if path.is_empty() or line <= 0:
        return _router._fail("VALIDATION_ERROR", "path and line required")
    
    var debugger = _router._debugger
    if debugger == null or debugger._session_id < 0:
        return _router._fail("PRECONDITION_FAILED", "No active debug session", "play_session")
    
    var session = debugger.get_session(debugger._session_id)
    session.set_breakpoint(path, line, true)
    return _router._ok({"breakpoint_set": true, "path": path, "line": line})
```

**Validation**: Run a test project, set breakpoint, play scene, observe if game pauses at breakpoint.

### Prototype B: Probe Enhancement (game side)

Extend `mcp_runtime_probe.gd`:

```gdscript
# Add to _capture match:
"force_break":
    EngineDebugger.debug(true, false)
    return true
```

**Validation**: Send `godot_mcp:force_break` from editor, check if game pauses.

### Prototype C: Message Name Discovery

Test protocol message names for step/continue:

```gdscript
# Try each candidate:
session.send_message("debugger_step", [])
session.send_message("debugger_next", [])
session.send_message("debugger_continue", [])
session.send_message("godot_mcp:step", [])  # custom channel won't work for built-in
```

The built-in debugger messages likely use **no prefix** or a **`debugger:`** prefix that is NOT routed to custom plugins.

**Key realization**: Custom `EditorDebuggerPlugin._has_capture()` only receives messages matching its registered prefix. Built-in debugger messages use a different prefix (probably `debugger:` or no prefix) and are handled by the built-in ScriptDebugger plugin, NOT our custom plugin.

This means we **cannot intercept** stack frames, breakpoint hits, or step confirmations from the built-in debugger through our custom plugin.

**Workaround**: Use the **ScriptEditorDebugger** internal API? But it's not exposed to GDScript...

---

## 8. Updated Verdict

### What IS Feasible (High Confidence)

1. ✅ **Breakpoint injection** via `EditorDebuggerSession.set_breakpoint()`
2. ✅ **Breakpoint removal** via `set_breakpoint(path, line, false)` or `EngineDebugger.remove_breakpoint()`
3. ✅ **Clear all breakpoints** via `EngineDebugger.clear_breakpoints()`
4. ✅ **Forced break** via `EngineDebugger.debug(true, false)` from probe

### What REQUIRES PROTOCOL HACKS (Medium Confidence)

5. ⚠️ **Step over / step into / continue** — Likely require sending raw protocol messages. Need to inspect Godot C++ source for exact message names. Risk: message names may change between 4.4/4.5/4.6.

### What IS DIFFICULT / MAY REQUIRE FALLBACK (Low Confidence)

6. ⚠️ **Stack frame capture** — Custom plugins cannot intercept built-in debugger stack messages. May require:
   - Engine modification (out of scope)
   - Or game-side cooperative stack dumping (probe injects `get_stack()` call?)
   - Or log-point fallback

7. ⚠️ **Expression evaluation in stack context** — `_debug_parse_stack_level_expression` is not exposed to GDScript. `Expression` class lacks stack context access.

---

## 9. Recommendation: GO with Tiered Implementation

### Tier 1 (Immediate): Breakpoint Control
- `set_breakpoint`, `remove_breakpoint`, `clear_breakpoints`, `force_break`
- These use documented, stable APIs.
- **Effort**: 1-2 days.

### Tier 2 (Research-dependent): Step/Continue
- `step_over`, `step_into`, `continue_execution`
- Requires discovering exact protocol message names from Godot source.
- **Effort**: 2-3 days if message names are stable; 1-2 weeks if we need version branching.

### Tier 3 (Advanced): Stack & Eval
- `get_stack_frames`, `evaluate_expression`
- May require creative workarounds or acceptance of limited functionality.
- **Effort**: 1-2 weeks; may partially land as "cooperative debugging" where the probe actively reports state.

### Tier 4 (Fallback): Log-Point Debugging
- If Tier 3 is impossible, implement log-point injection + `run_and_capture` parsing.
- **Effort**: 3-4 days.
- **Value**: Still gives agents the ability to "watch" variables at specific lines without true debugger integration.

---

## 10. Next Steps

1. **Prototype Tier 1** (`set_breakpoint` + `force_break`) — validate basic API works.
2. **Research protocol messages** — inspect Godot 4.4/4.5/4.6 C++ source for `debugger_step`, `debugger_next`, `debugger_continue` string constants.
3. **Decide on Tier 3 approach** — either commit to cooperative stack dumping or switch to log-point fallback.
4. **Write implementation spec** for whichever approach is chosen.

---

## 11. Research Notes & Sources

### Sources Consulted
- Context7: `/godotengine/godot-docs` — `class_editordebuggersession.md`, `class_editordebuggerplugin.md`, `class_enginedebugger.md`, `class_scriptlanguageextension.md`
- Nwiro Pro website: https://leartesstudios.com/nwiro
- Existing `godot-mcp` code: `mcp_debugger.gd`, `mcp_runtime_probe.gd`, `runtime_session.gd`, `runtime_inspect.gd`

### Key API References

| API | Location | Status |
|---|---|---|
| `EditorDebuggerSession.set_breakpoint(path, line, enabled)` | `class_editordebuggersession.md` | ✅ Public |
| `EngineDebugger.debug(can_continue, is_error_breakpoint)` | `class_enginedebugger.md` | ✅ Public |
| `EngineDebugger.remove_breakpoint(source, line)` | `class_enginedebugger.md` | ✅ Public |
| `EngineDebugger.clear_breakpoints()` | `class_enginedebugger.md` | ✅ Public |
| `EditorDebuggerSession.send_message(msg, data)` | `class_editordebuggersession.md` | ✅ Public |
| `_debug_parse_stack_level_expression(...)` | `class_scriptlanguageextension.md` | ⚠️ Internal |
| `EditorDebuggerPlugin._breakpoint_set_in_tree(...)` | `class_editordebuggerplugin.md` | ❌ Private |
| Step/Continue/Stack methods | Not found in docs | ❓ Unknown |

---

*End of Feasibility Document*
