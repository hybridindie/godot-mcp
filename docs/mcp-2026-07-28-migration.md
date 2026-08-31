# MCP 2026-07-28 Migration Plan

> Tracking issue: [#386](https://github.com/hybridindie/godot-mcp/issues/386) ·
> Status: **planned** — no implementation work is gated on this document.
> Related: godot-agents client follow-up (see §5), pinned FastMCP `4.0.0b3` (#311).

## 1. What the spec changed

The MCP spec's **2026-07-28 revision** removes sessions and the `initialize`
handshake entirely:

- **Stateless protocol** — no session lifecycle, no server-initiated requests
  riding a session back-channel.
- **Per-request `_meta`** carries version/capabilities instead of the
  handshake negotiation.
- **Cross-call state** moves to **explicit handles**: server-minted tokens
  passed as ordinary tool arguments (the pattern `request_state` already uses).
- **`server/discover`** replaces handshake capability probing.

Prior revisions (2025-11-25 / 2025-06-18) remain published; we are pinned to
FastMCP 4.0.0b3, which speaks 2025-era session semantics — but FastMCP 4.0's
`Client` already **negotiates sessionless by default**, which is why the real
client traffic godot-mcp sees is the sessionless `2026-07-28` protocol.

## 2. Inventory: what rides on session affinity

Audited via graph query + source scan (`grep session_id|on_initialize` under
`mcp_server/`). **Finding: the server is already sessionless-native.** The
issue's premise — "ToolsetMiddleware keys enable/disable on
`context.session_id`" — was fixed in #370/#364 (merged 2026-08-27), which
removed per-session isolation as dead code on the sessionless protocol.

| Stateful surface | Where it lives | Session dependency | Status |
|---|---|---|---|
| Toolset enable/disable | `ToolsetMiddleware` (`toolset_middleware.py`) | **None** — single server-global enabled set (#364) | 2026-native |
| Destructive-tool approval guard | `ApprovalMiddleware` (`approval_middleware.py`) | **None** — `InputRequiredResult` + `request_state` round-trip, "durable, no server-side state" (#346) | 2026-native (handles pattern) |
| `ctx.info` / `ctx.report_progress` | `tools/_progress.py` `safe_info` / `safe_progress` | **None** — guarded no-op in the detached task session (`task=True`, #331) | 2026-tolerant |
| Bridge request/response correlation | `bridge.py` (`id` → waiter) | **None** — envelope `id` correlation, concurrency-safe | Protocol-agnostic |
| ReadCache / `gather_reads` | `harness.py` | Client process state — not server state; client decides scoping | N/A (client-side) |

Two invariants are **enforced by contract tests**:

- `tests/contract/test_toolset_global_state.py` — no `on_initialize` override;
  enable/disable persist across independent sessionless clients.
- `tests/contract/test_approval_guard.py` — the guard round-trips tool +
  params + safety class through `request_state`; second round reads
  `ctx.input_responses`.

And a **source-shape guard** added by this issue:

- `tests/contract/test_sessionless_invariants.py` — AST scan over
  `mcp_server/**`: no module may read `.session_id` / `.session`, name a
  `session_id` binding, or define `on_initialize` / `on_new_session` /
  `on_session_end`. A drift back toward session keying fails preflight, not
  production.

## 3. The design: explicit handles, not session affinity

The 2026-native equivalent of "enable + mutate share one session" is already
the *shape* the server exposes — but the mechanism is deliberately **coarser
and simpler** than the spec's per-consumer handles:

### Decision

- **No `session_handle` / `toolset_grant` token.** godot-mcp is a
  **single-user, local server** (one client per Godot instance, localhost-only,
  no auth in v1). A server-global enabled set (#364) is the correct scope:
  minting per-call handles would add a token-passing tax to every gated call
  and re-introduce the failure mode it exists to avoid (a sessionless client
  dropping the handle → gating silently no-ops).
- **`request_state` is our handle pattern** for anything that genuinely needs
  per-call round-trip state (today: the approval guard). The spec's
  server-minted-handles recommendation is satisfied by this where it matters.
- **The one behavioral inversion vs. the spec's default**: where a
  spec-default server would scope a grant to the caller, godot-mcp's grants
  are visible to every client of the process. This is documented, intended
  (#364), and tested.

### Risks

| Risk | Assessment |
|---|---|
| **Silent gating bypass in sessionless clients** (the issue's named risk) | **Eliminated by #364's design.** With server-global state there is no affinity scope to lose: a stateless client that enables in call N sees the grant in call N+1 even across reconnects. The no-op bypass existed only under `session_id` keying. |
| Concurrent multi-client interference | Accepted: single-user server, documented. A long-lived client A enabling a toolset changes what client B sees in `list_tools` — that is the design. If godot-mcp ever grows multi-tenant, the handle design becomes mandatory; until then the global set keeps the surface honest. |
| FastMCP removes session-era APIs we still touch | Low: the server relies on no session APIs (see §2). The migration surface is FastMCP's, not ours. |
| `task=True` detached sessions (`ctx.session is None`) | Handled by `safe_info`/`safe_progress` guards (#331) and the guard-pattern rule in `.opencode/rules/async-patterns.md` (no `ctx.elicit()`, no `Middleware.on_initialize`). |

## 4. FastMCP dependency

**Blocking for implementation, not for the plan** (per the issue). Nothing in
`mcp_server/` needs to change when FastMCP ships 2026-spec support:

- The handshake / `_meta` / `server/discover` mechanics are framework-owned.
- Our contract tests exercise the server through FastMCP's `Client`, which
  already negotiates sessionless — the tests stay valid across the transition.
- Watch: PrefectHQ/fastmcp's 4.0 stable release and its 2026-07-28 revision
  support timeline. When it lands, re-run the contract suite; expected delta
  is zero. If FastMCP instead removes session-era defaults (e.g. forces
  `_meta` versioning), the surfaces to touch are the middleware base classes
  only — the source-shape guard keeps application code clean in the meantime.

## 5. godot-agents follow-up (client side)

godot-agents' AGENTS.md documented the sessionless bypass risk under
per-session keying; **that concern is void** — with server-global state, its
`_ensure_or_return_error` pattern (enable → verify visible → mutate) works
regardless of affinity scope, including across fresh connections. The
remaining client-side follow-up (filed on merge of this plan):

- Prefer `structuredContent` over text parsing in `MCPResult` (#385's
  client half).
- Drop any residual assumption that enable+mutate must share one
  `ClientSession` — a reconnect between them no-ops nothing.