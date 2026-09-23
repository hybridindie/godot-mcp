@tool
class_name MCPAutoRefresh
extends RefCounted
## Opt-in timer-based filesystem auto-refresh (issue #561).
##
## The editor's external-file detection is window-focus-driven: files changed
## by an agent/git/another tool while the editor is unfocused stay invisible
## until a human clicks into Godot. This helper drives an opt-in periodic
## EditorFileSystem.scan() so external edits are picked up without focus.
##
## Pure decision logic (opt-in flag + is_scanning() re-entrancy guard), with
## the environment access behind a Callable seam so it is verifiable
## headlessly (godot/tests/auto_refresh_smoke.gd). The plugin owns the timer
## and the dock toggle; this helper owns the decision.

const ENV_VAR := "GODOT_MCP_AUTO_REFRESH"
const DEFAULT_INTERVAL := 10.0

## Whether the refresh is enabled: the env var opts in ("1", "true", "yes",
## case-insensitive); unset/anything else = off (byte-identical to today).
static func enabled_from_env(env_getter: Callable = Callable(OS, "get_environment")) -> bool:
	var raw: String = str(env_getter.call(ENV_VAR)).to_lower()
	return raw in ["1", "true", "yes"]


## The scan interval from the env var (seconds), clamped to a sane range; 0/absent = default.
static func interval_from_env(env_getter: Callable = Callable(OS, "get_environment"), default: float = DEFAULT_INTERVAL) -> float:
	var raw := str(env_getter.call("GODOT_MCP_AUTO_REFRESH_INTERVAL"))
	if raw.is_empty():
		return default
	var parsed := raw.to_float()
	if parsed <= 0.0:
		return default
	return maxf(parsed, 2.0)  # floor: don't hammer the filesystem


## The timer tick's decision: call scan() only when enabled AND no scan is in
## flight (re-entrancy: scan() against an in-flight scan is unsafe — the
## #417 deferred-scan path and the #453 read-side guard key on is_scanning()).
## `fs` is duck-typed ({is_scanning, scan}) via the injected seam.
static func tick(enabled: bool, fs: Object) -> bool:
	if not enabled or fs == null:
		return false
	if fs.is_scanning():
		return false  # never stack a scan on an in-flight one
	fs.scan()
	return true