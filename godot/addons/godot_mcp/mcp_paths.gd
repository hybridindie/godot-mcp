@tool
class_name MCPPaths
extends RefCounted
## res:// containment, the GDScript mirror of the server's
## mcp_server/paths.py::escapes_res_root (issue #909).
##
## A dependency-free leaf: no preloads and no other addon classes, so any
## script (type_coerce.gd included) can call it without an import cycle.
## Defense in depth — the server's ResPath rejects these paths first.

const SCHEME := "res://"
const _DRIVE_LETTERS := "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


## "" when `path` is a res:// path contained in the project root, else a hint
## for a VALIDATION_ERROR. Refused: a missing scheme, a backslash, a Windows
## drive (`C:`), an absolute rest (`res:///abs`), and any `..` that climbs above
## root at any depth. `res://a/../b.gd` stays inside.
##
## The normaliser is a hand-rolled component walk rather than
## String.simplify_path(): how that collapses repeated leading `..` differs
## across engine versions, and on an older engine `res://../../x` could
## collapse to a contained-looking `x`. The walk matches posixpath.normpath.
static func res_path_error(path: String) -> String:
	if not path.begins_with(SCHEME):
		return "'%s' must be a res:// path inside the project." % path
	if path.contains("\\"):
		return "'%s' escapes the project root (res://): use '/' separators, not backslashes." % path
	var rest := path.substr(SCHEME.length())
	if rest.length() >= 2 and rest[1] == ":" and _DRIVE_LETTERS.contains(rest[0]):
		return "'%s' escapes the project root (res://): a Windows drive is not allowed." % path
	if rest.begins_with("/"):
		return "'%s' escapes the project root (res://): the path after res:// is absolute." % path
	var depth := 0
	for part: String in rest.split("/"):
		if part.is_empty() or part == ".":
			continue
		if part == "..":
			if depth == 0:
				return "'%s' escapes the project root (res://)." % path
			depth -= 1
		else:
			depth += 1
	return ""


## res_path_error for an optional path-or-UID param: "" also for an empty value
## ("not specified") and a uid:// reference, which the UID database resolves
## to a project path and cannot traverse.
static func optional_res_path_error(path: String) -> String:
	if path.is_empty() or path.begins_with("uid://"):
		return ""
	return res_path_error(path)
