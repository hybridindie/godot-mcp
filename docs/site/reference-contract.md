---
type: index
title: "The compatibility contract"
description: "What the contract covers, why it has its own version, and how a client negotiates compatibility with a server."
created: 2026-10-18
updated: 2026-10-18
---

# The compatibility contract

Godot Editor MCP is built to be consumed by other software — an agent harness, an
orchestrator, an eval runner, or your own client. The **contract** is the stable boundary
between that software and this server.

It is one idea with two parts:

1. **The surface** clients build against: tool names, parameters, result fields, the
   envelope, error codes, and safety semantics.
2. **A compatibility number** for that surface: `contract_version`, with
   `min_compatible_contract` as the oldest client contract the server still serves.

“Contract tests” are the tests that pin the surface. `contract_version` is the counter for
the guarantees those tests protect.

## What the contract covers

| Surface | What is promised |
|---------|------------------|
| Tools | Exposed names, input parameter names/types/requiredness/defaults, and toolset categories |
| Results | Result-model fields and their meaning, including honesty fields (`persisted`, `undoable`, `aborted_at`, `rescan_pending`, …) |
| Values | JSON value shapes for Godot types (`Vector2`, `Color`, `Rect2`, `NodePath`, …) |
| Envelope | `{id, command, params}` → `{id, ok, result, error, hint, required, next_call?}` |
| Errors | The stable `ErrorCode` enum and the recovery contract (`hint`, `required`, optional `next_call`) |
| Safety | `read_only` / `mutating` / `destructive` / `runtime`, plus `dry_run` and `confirm` requirements |
| Discovery | `godot_get_server_info` fields clients use to negotiate and orient |

## What the contract does not cover

- **The CalVer build version.** `version` (`YYYY.MM.DD[.N]`, where `.N` is a same-day
  revision) moves on every release, including additive and internal changes.
- **The MCP protocol revision** (`2026-07-28`) or the FastMCP version.
- **Server↔addon version matching.** `version_notice` handles that separately; both
  halves should come from the same release.
- **Internal addon handler names** (`cmd_*`). The server and addon ship together; clients
  do not negotiate against them.
- **Your game vocabulary.** Tools and prompts that know about towers, waves, or enemies
  belong in a consumer project, not this contract.

## Why it has its own version

`version` answers **“which build is this?”** It cannot answer **“will my client still
work?”**, because most releases add tools and optional fields without breaking anything.
Gating on CalVer would force every consumer to update on every release.

`contract_version` answers the compatibility question:

- It is a monotonic integer, not a date.
- It moves only when a client could break.
- It lets a client fail fast at startup with a precise message instead of discovering the
  break mid-task.
- It lets the server keep serving older clients through `min_compatible_contract`.

## The two numbers

`godot_get_server_info` returns both, alongside the CalVer build:

```jsonc
{
  "version": "…",                  // CalVer build — changes every release
  "contract_version": 1,           // newest contract this server serves
  "min_compatible_contract": 1     // oldest client contract still served
}
```

Current values are `contract_version = 1` and `min_compatible_contract = 1`.

## How negotiation works

A client carries the contract it was built against, `K`. The server advertises its newest
contract, `C`, and its oldest compatible contract, `M`. The client is compatible when:

```text
M  ≤  K  ≤  C
```

| Condition | Meaning | What to do |
|-----------|---------|------------|
| `K < M` | The client is too **old** — the server no longer serves that contract. | Upgrade the client, or use a server release that still serves `K`. |
| `M ≤ K ≤ C` | The contracts overlap. | Compatible. |
| `K > C` | The client is too **new** — it expects behavior this server does not have. | Upgrade the server. |

Inside the compatible range the additive guarantee applies: unknown fields are safe to
ignore, and the tools, parameters, and result fields the client already uses keep working.

## What bumps the contract

**Breaking — bump `CONTRACT_VERSION`:**

- removing or renaming a tool
- changing or removing a required parameter
- changing a result-model field (name, type, or meaning)
- changing the bridge-envelope shape
- changing the meaning of an existing error code
- changing a tool's safety class or its `dry_run` / `confirm` requirement

**Additive — do not bump:**

- adding a tool, toolset, prompt, or resource
- adding an optional parameter or result field
- adding a new error code
- documenting a new value shape without changing existing ones

When the floor moves — when the server stops serving an older client contract — update
`MIN_COMPATIBLE_CONTRACT` as well. Both values live in
[`mcp_server/__init__.py`](https://github.com/hybridindie/godot-mcp/blob/main/mcp_server/__init__.py).

## Check it at startup

A consumer that pins the contract should assert it once, before doing work:

```python
info = await client.call_tool("godot_get_server_info", {})
compatible = (
    info["min_compatible_contract"]
    <= CLIENT_CONTRACT
    <= info["contract_version"]
)
if not compatible:
    raise RuntimeError(f"Godot Editor MCP contract mismatch: {info}")
```

That turns an incompatible server into one clear startup error instead of a sequence of
mysterious tool failures.

## Where it lives

| Thing | Location |
|-------|----------|
| Version constants | `mcp_server/__init__.py` (`CONTRACT_VERSION`, `MIN_COMPATIBLE_CONTRACT`) |
| Runtime exposure | `godot_get_server_info` (`contract_version`, `min_compatible_contract`) |
| Authoritative per-tool spec | [`docs/tool-contracts.md`](https://github.com/hybridindie/godot-mcp/blob/main/docs/tool-contracts.md) |
| Envelope rules | [The JSON envelope](architecture/envelope.md) |
| Pinning tests | `tests/contract/` — bridge envelope, output schema, diagnostics, capabilities |
| Consumer guidance | [Consumer integration](reference-consumers.md) |

## Related

- **[Concepts](concepts.md)** — the mental model behind the surface.
- **[Errors & recovery](reference-errors.md)** — the stable error enum.
- **[Consumer integration](reference-consumers.md)** — pinning the contract from another project.
