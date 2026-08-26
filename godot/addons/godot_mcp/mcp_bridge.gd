@tool
class_name MCPBridge
extends Node
## WebSocket client inside the editor plugin (issue #3; direction inverted in #276).
##
## Connects OUT to the MCP server's bridge listener (default ws://127.0.0.1:9080) and
## reconnects with backoff whenever the link is down — the editor is the party that
## comes and goes, so it owns reconnection (see docs/architecture.md). Pumps the peer
## every frame in _process: parse JSON command envelopes, dispatch through
## MCPCommandRouter, and send back JSON response envelopes. localhost-only, no auth in v1.
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

var _peer: WebSocketPeer = null
var _router: MCPCommandRouter = null
var _url := DEFAULT_URL
var _active := false  # whether we should keep a connection alive (start/stop)
var _status: Status = Status.DISCONNECTED
var _retry_delay := _RETRY_MIN
var _retry_remaining := 0.0  # seconds until the next reconnect attempt


func _init(router: MCPCommandRouter = null) -> void:
	_router = router if router != null else MCPCommandRouter.new()


## Begin connecting (and reconnecting) to the server. Returns the first attempt's Error.
func start(url: String = DEFAULT_URL) -> int:
	_url = url
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


func is_connected_to_server() -> bool:
	return _status == Status.CONNECTED


func get_status() -> Status:
	return _status


## Open a fresh peer and start the non-blocking connect. _process drives the rest.
func _open() -> int:
	_peer = WebSocketPeer.new()
	var err := _peer.connect_to_url(_url)
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


func _handle_text(text: String) -> void:
	var response: Dictionary
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		response = {"id": "", "ok": false, "error": "VALIDATION_ERROR", "hint": "Malformed JSON envelope."}
	else:
		response = _router.handle(parsed)
		command_received.emit(str((parsed as Dictionary).get("command", "?")))
	if _peer != null:
		_peer.send_text(JSON.stringify(response))


func _set_status(status: Status) -> void:
	if status != _status:
		_status = status
		connection_changed.emit(status)
