@tool
class_name MCPReceipt
extends RefCounted
## Change receipts for mutating handlers (issue #756).
##
## Built from the handler's read-back, never from the request: a write that the
## engine silently dropped is `noop`, not `updated`. `changes` is bounded so a
## large batch cannot flood the wire; eviction is counted via `truncated`.

const Coerce := preload("./type_coerce.gd")
const MAX_CHANGES := 50


## One changed path (node path or res:// file). Values are JSON-coerced.
static func change(path: String, op: String, before: Variant, after: Variant) -> Dictionary:
	return {
		"path": path,
		"op": op,
		"before": Coerce.to_json(before),
		"after": Coerce.to_json(after),
	}


## A receipt body: status + bounded change list.
static func make(status: String, changes: Array) -> Dictionary:
	var truncated := changes.size() > MAX_CHANGES
	var bounded := changes.slice(0, MAX_CHANGES) if truncated else changes
	return {"status": status, "changes": bounded, "truncated": truncated}
