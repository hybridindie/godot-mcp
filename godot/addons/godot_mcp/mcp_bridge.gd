@tool
class_name MCPBridge
extends Node
## WebSocket client inside the editor plugin (issue #3; direction inverted in #276).
##
## Connects OUT to the MCP server's bridge listener (default ws://127.0.0.1:9080) and
## reconnects with backoff whenever the link is down — the editor is the party that
## comes and goes, so it owns reconnection (see docs/architecture.md). Pumps the peer
## every frame in _process: parse JSON command envelopes, dispatch through
## MCPCommandRouter, and send back JSON response envelopes. Optional shared-token
## auth (issue #538): when GODOT_MCP_BRIDGE_TOKEN is set, the FIRST message after
## connect authenticates the editor ({command: cmd_auth, params:{token}}); a
## mismatch gets a structured refusal and this side drops into its normal
## reconnect/backoff loop (the dock log shows the refusal reason each attempt).
##
## API verified against the Godot 4 docs (class_websocketpeer): WebSocketPeer
## connect_to_url / poll / get_ready_state (STATE_CONNECTING/OPEN/CLOSING/CLOSED) /
## get_available_packet_count / get_packet / send_text (see .opencode/rules/addon.md).

## Mirrors MCPStatusDock.ConnectionStatus ordering so the plugin can map directly.
enum Status { DISCONNECTED, CONNECTING, CONNECTED }

const DEFAULT_URL := "ws://127.0.0.1:9080"
# Reconnect backoff: start small, double on each failed attempt, capped — so a server
# that isn't up yet (or that restarts) is found again without hammering it.
const _RETRY_MIN := 0.5
const _RETRY_MAX := 5.0

signal connection_changed(status: Status)
signal command_received(command: String)
## Emitted after each command completes with the command name and handler
## execution time in milliseconds (#520: the addon only ever *responds* to
## commands, so a round-trip "latency" can't be measured here — one honest
## exec_ms replaces the mislabeled latency arg).
signal command_completed(command: String, exec_ms: float)

# _peer is untyped so tests can inject a send-recording stand-in (peer_hello
# smoke, #537); production only ever assigns a real WebSocketPeer.
var _peer = null
var _router: MCPCommandRouter = null
var _url := DEFAULT_URL
var _active := false  # whether we should keep a connection alive (start/stop)
var _status: Status = Status.DISCONNECTED
var _retry_delay := _RETRY_MIN
var _retry_remaining := 0.0  # seconds until the next reconnect attempt
# Opt-in shared-token auth (issue #538): read once at start; never logged.
var _auth_token := ""


func _init(router: MCPCommandRouter = null) -> void:
	_router = router if router != null else MCPCommandRouter.new()


## Begin connecting (and reconnecting) to the server. Returns the first attempt's Error.
func start(url: String = DEFAULT_URL, auth_token: String = "") -> int:
	_url = url
	# Token resolution mirrors GODOT_MCP_BRIDGE_URL (godot_mcp.gd): explicit arg
	# wins, else the env var, else no auth. Never logged.
	_auth_token = auth_token if not auth_token.is_empty() else OS.get_environment("GODOT_MCP_BRIDGE_TOKEN")
	_active = true
	_retry_delay = _RETRY_MIN
	_retry_remaining = 0.0
	return _open()


func stop() -> void:
	_active = false
	if _peer != null:
		_peer.close()
		_peer = null
	_set_status(Status.DISCONNECTED)


## Stop the bridge and release the router, breaking the router/handler reference
## cycle so the router, its handler instances and their scripts can be freed on
## plugin exit. RefCounted cycles never reach a zero reference count on their own
## (see the RefCounted class reference), so the plugin calls this from _exit_tree().
func dispose() -> void:
	stop()
	if _router != null:
		_router.dispose()
		_router = null


func is_connected_to_server() -> bool:
	return _status == Status.CONNECTED


func get_status() -> Status:
	return _status


## Open a fresh peer and start the non-blocking connect. _process drives the rest.
func _open() -> int:
	_peer = WebSocketPeer.new()
	var err: int = _peer.connect_to_url(_url)
	if err != OK:
		# Bad URL / invalid state: drop the peer and back off; _process retries.
		push_error("godot_mcp: connect_to_url(%s) failed (error %d)" % [_url, err])
		_peer = null
		_set_status(Status.DISCONNECTED)
		_schedule_retry()
	else:
		_set_status(Status.CONNECTING)
	return err


func _process(delta: float) -> void:
	if not _active:
		return
	if _peer == null:
		# Disconnected: count down the backoff, then try again.
		_retry_remaining -= delta
		if _retry_remaining <= 0.0:
			_open()
		return

	_peer.poll()
	match _peer.get_ready_state():
		WebSocketPeer.STATE_OPEN:
			if _status != Status.CONNECTED:
				_retry_delay = _RETRY_MIN  # connected: reset the backoff
				_send_auth()  # #538: authenticate FIRST when a token is configured
				_send_peer_hello()  # #537: announce identity (project_path etc.)
			_set_status(Status.CONNECTED)
			while _peer.get_available_packet_count() > 0:
				_handle_text(_peer.get_packet().get_string_from_utf8())
		WebSocketPeer.STATE_CONNECTING:
			_set_status(Status.CONNECTING)
		WebSocketPeer.STATE_CLOSING:
			pass  # keep polling for a clean close
		WebSocketPeer.STATE_CLOSED:
			# Server gone / connect failed: drop and schedule a backed-off reconnect.
			_peer = null
			_set_status(Status.DISCONNECTED)
			_schedule_retry()


func _schedule_retry() -> void:
	_retry_remaining = _retry_delay
	_retry_delay = minf(_retry_delay * 2.0, _RETRY_MAX)


## Announce this editor's identity to the server (#537): a control envelope the
## server consumes without replying (no waiter). The server keeps it and
## surfaces the connected editor's project path in godot_get_server_info, and
## logs a structured "peer replaced" entry naming both paths when a second
## editor takes over — silence is what a replaced agent can't diagnose.
func _send_peer_hello() -> void:
	if _peer == null:
		return
	var info: Dictionary = {
		"id": "peer_hello",
		"command": "cmd_peer_hello",
		"params": {
			"project_path": ProjectSettings.globalize_path("res://"),
			"godot_version": str(Engine.get_version_info().get("string", "")),
			"addon_version": _addon_version(),
		},
	}
	_peer.send_text(JSON.stringify(info))


## Authenticate the connection (issue #538): the FIRST message after connecting
## when a token is configured. The server verifies it before serving anything —
## a mismatch answers a structured refusal envelope and closes the peer, which
## drops this side into the normal reconnect/backoff loop (the dock shows the
## refusal reason each attempt until the tokens agree). With no token configured
## nothing is sent — zero-config localhost dev stays byte-identical.
func _send_auth() -> void:
	if _peer == null or _auth_token.is_empty():
		return
	var envelope: Dictionary = {
		"id": "auth",
		"command": "cmd_auth",
		"params": {"token": _auth_token},
	}
	_peer.send_text(JSON.stringify(envelope))


func _addon_version() -> String:
	var addon_version := ""
	var cfg := ConfigFile.new()
	if cfg.load("res://addons/godot_mcp/plugin.cfg") == OK:
		addon_version = str(cfg.get_value("plugin", "version", ""))
	return addon_version


func _handle_text(text: String) -> void:
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) == TYPE_DICTIONARY:
		var d := parsed as Dictionary
		# Server→addon push (issue #538): an ok-shaped envelope is NOT a command —
		# it is the server refusing or notifying us (today: the auth refusal).
		# Log its hint for the dock, never echo a response to a response, and
		# drop the link so the reconnect loop retries (with backoff) once the
		# operator fixes the mismatched GODOT_MCP_BRIDGE_TOKEN.
		if d.has("ok") and not d.has("command"):
			if bool(d.get("ok", true)) == false:
				push_error("godot_mcp: server refused this editor — %s: %s" % [
					str(d.get("error", "ERROR")), str(d.get("hint", "")),
				])
				_peer.close()
			return
	var response: Dictionary
	var cmd_name := "?"
	var send_time := Time.get_ticks_usec()
	if typeof(parsed) != TYPE_DICTIONARY:
		response = {"id": "", "ok": false, "error": "VALIDATION_ERROR", "hint": "Malformed JSON envelope."}
	else:
		var d2 := parsed as Dictionary
		cmd_name = str(d2.get("command", "?"))
		response = _router.handle(d2)
		command_received.emit(cmd_name)
	if _peer != null:
		_peer.send_text(JSON.stringify(response))
	# Handler execution time only (#520): the addon responds to commands, it
	# never originates them, so there is no send-side timestamp to diff —
	# exec_ms is the one honest number this side can measure.
	var exec_ms := (Time.get_ticks_usec() - send_time) / 1000.0
	command_completed.emit(cmd_name, exec_ms)


func _set_status(status: Status) -> void:
	if status != _status:
		_status = status
		connection_changed.emit(status)