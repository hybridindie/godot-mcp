# Harness performance patterns

The Godot editor is **single-threaded**: the addon drains queued command packets once
per `_process` frame and executes them serially on the main thread (~50–100ms/command).
The server can't parallelize past that — the only levers are **fatter commands** and
**fewer commands**. This doc collects the patterns a scripted harness (the eval runner,
any MCP client) uses to stay off that ceiling. They are game-agnostic and complement the
server-side wins (#166 dropped a redundant preflight round-trip per mutation; #168 added
a lightweight `get_scene_tree` mode).

## 1. Batch arbitrary commands — `run_commands` (#167)

When you have N commands to run, send them as **one** `run_commands` batch instead of N
tool calls. The addon executes the whole list in a single frame and returns one envelope
per command, so N round-trips collapse to one. Each sub-mutation still wraps its own
`UndoRedo` action; order is preserved.

```jsonc
run_commands({
  "commands": [
    {"command": "create_node", "params": {"parent_path": ".", "node_type": "Node2D", "name": "Enemies"}},
    {"command": "set_node_property", "params": {"node_path": "Enemies", "property": "position", "value": [100, 0]}}
  ],
  "stop_on_error": true   // halt at the first failure; false runs them all
})
```

Use this for **ordered** sequences and for writes. `run_commands` cannot be nested.

## 2. Pipeline independent reads — `gather_reads` (#169)

A discovery phase often issues many *independent* reads (`get_scene_tree`,
`get_node_properties`, …). Awaiting each in turn pays ~one frame of latency per read. The
bridge correlates responses by `id`, so many reads can be **in flight at once**: fired
together, the addon answers them all in ~one frame — an O(N)-frame discovery phase becomes
~O(1).

The helper `mcp_server.harness.gather_reads` runs in the **client/harness process**
(it is not an MCP tool) and wraps a connected `Bridge`:

```python
from mcp_server.harness import gather_reads

tree, player_props, enemy_props = await gather_reads(bridge, [
    ("cmd_get_scene_tree", {"max_depth": 2, "lightweight": True}),
    ("cmd_get_node_properties", {"node_path": "Player"}),
    ("cmd_get_node_properties", {"node_path": "Enemy"}),
])
```

Only read-only commands pipeline safely — the editor is a single writer, so writes must
stay ordered. `gather_reads` rejects any non-read command with a `ValueError`; batch
writes with `run_commands` instead. See `READ_ONLY_COMMANDS` in `mcp_server/harness.py`
for the allowed set.

> Pipeline reads vs. `run_commands` for reads: both get N reads back in ~one frame.
> `run_commands` is one tool call (good when going through the MCP tool surface);
> `gather_reads` is a direct-bridge helper (good for a harness that already holds a
> `Bridge`, e.g. the eval runner). Pick whichever your call path already uses.

## 3. Cache stable reads — `ReadCache` (#170)

Scene structure and node-property lists don't change *between* mutations, yet harnesses
often re-fetch them every step. `mcp_server.harness.ReadCache` memoizes read-only results
per session and drops them on a write, so repeated identical reads cost one round-trip
instead of many — and don't re-enter the agent's context as fresh tokens.

```python
from mcp_server.harness import ReadCache

cache = ReadCache(bridge)          # one instance per session
tree = await cache.read("cmd_get_scene_tree", {"max_depth": 2})
tree_again = await cache.read("cmd_get_scene_tree", {"max_depth": 2})  # cache hit, no round-trip

# Route mutations through write(), which invalidates the cache so no stale read survives:
await cache.write("cmd_set_node_property", {"node_path": "Player", "property": "visible", "value": False})
fresh = await cache.read("cmd_get_scene_tree", {"max_depth": 2})       # re-fetched
```

The cache is **per session** (one `ReadCache` per session) — unlike the old server-side
preflight cache, which was a process-global cleared on every mutation and could bleed
across sessions (removed in #166). If a mutation is issued *outside* the cache (not via
`write`), call `cache.invalidate()` so the next read is fresh. `read` accepts only
read-only commands (see `READ_ONLY_COMMANDS`); a mutation raises `ValueError`.
