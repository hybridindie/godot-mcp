@tool
class_name MCPBridge
extends Node
## WebSocket server inside the editor plugin (issue #3).
##
## Listens on localhost via TCPServer, upgrades the accepted stream to a
## WebSocketPeer, and pumps it every frame in _process: parse JSON command
## envelopes, dispatch through MCPCommandRouter, and send back JSON response
## envelopes. Single-client (one editor ↔ one server); a new connection replaces
## the previous peer. localhost-only, no auth in v1.
##
## API verified against Godot 4 docs: TCPServer.listen/take_connection,
## WebSocketPeer.accept_stream/poll/get_ready_state/get_packet/send_text
## (see .claude/rules/addon.md).

## Mirrors MCPStatusDock.ConnectionStatus ordering so the plugin can map directly.
enum Status { DISCONNECTED, CONNECTING, CONNECTED }

const DEFAULT_PORT := 9080
const BIND_ADDRESS := "127.0.0.1"

signal connection_changed(status: Status)
signal command_received(command: String)

var _tcp := TCPServer.new()
var _peer: WebSocketPeer = null
var _router: MCPCommandRouter = null
var _listening := false
var _status: Status = Status.DISCONNECTED


func _init(router: MCPCommandRouter = null) -> void:
	_router = router if router != null else MCPCommandRouter.new()


## Begin listening. Returns an Error code (OK on success).
func start(port: int = DEFAULT_PORT) -> int:
	var err := _tcp.listen(port, BIND_ADDRESS)
	_listening = err == OK
	if not _listening:
		push_error("godot_mcp: failed to listen on %s:%d (error %d)" % [BIND_ADDRESS, port, err])
	_set_status(Status.DISCONNECTED)
	return err


func stop() -> void:
	if _peer != null:
		_peer.close()
		_peer = null
	if _listening:
		_tcp.stop()
		_listening = false
	_set_status(Status.DISCONNECTED)


func is_listening() -> bool:
	return _listening


func _process(_delta: float) -> void:
	if not _listening:
		return
	_accept_pending()
	_pump_peer()


func _accept_pending() -> void:
	# Accept the newest connection; a fresh server connection replaces any old peer.
	while _tcp.is_connection_available():
		var conn := _tcp.take_connection()
		_peer = WebSocketPeer.new()
		_peer.accept_stream(conn)
		_set_status(Status.CONNECTING)


func _pump_peer() -> void:
	if _peer == null:
		return
	_peer.poll()
	match _peer.get_ready_state():
		WebSocketPeer.STATE_OPEN:
			_set_status(Status.CONNECTED)
			while _peer.get_available_packet_count() > 0:
				_handle_text(_peer.get_packet().get_string_from_utf8())
		WebSocketPeer.STATE_CLOSED:
			_peer = null
			_set_status(Status.DISCONNECTED)


func _handle_text(text: String) -> void:
	var response: Dictionary
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		response = {"id": "", "ok": false, "error": "VALIDATION_ERROR", "hint": "Malformed JSON envelope."}
	else:
		response = _router.handle(parsed)
		command_received.emit(str((parsed as Dictionary).get("command", "?")))
	_peer.send_text(JSON.stringify(response))


func _set_status(status: Status) -> void:
	if status != _status:
		_status = status
		connection_changed.emit(status)
