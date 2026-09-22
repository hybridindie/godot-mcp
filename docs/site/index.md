---
layout: home

hero:
  name: 'godot-mcp'
  text: 'Drive a live Godot editor from an AI agent'
  tagline: 'A generic, game-agnostic MCP server for AI-driven Godot development — inspect, mutate, run, and verify a real project over the Model Context Protocol. 186 tools across 29 gated toolsets.'
  actions:
    - theme: brand
      text: What & why
      link: ./what-why
    - theme: alt
      text: Getting Started
      link: ./getting-started
    - theme: alt
      text: LLM docs (llms.txt)
      link: /godot-mcp/llms.txt

features:
  - title: The editor is the participant
    details: Every action happens against the live editor — the same scene the human sees, with the editor's own undo stack covering agent actions. File-blind agents drift; this one doesn't.
  - title: Safety is a product, not a flag
    details: Every tool carries a safety class. Destructive tools require confirm. dry_run previews run the same persistence rule the real run will. All safety lives in the server — never in the addon.
  - title: 186 tools, gated on demand
    details: Only core + inspection are exposed by default. The agent enables toolsets as needed — a small surface keeps tool-selection sharp. New categories always register gated off.
  - title: Honest results, not optimistic ones
    details: Every mutation stamps a persistence verdict; batches report undoable and aborted_at; parse checks flag rescan_pending; timeouts are distinguished from crashes.
---

## The data path, end to end

Every agent action crosses four layers — each hop is contract-tested:

```mermaid
flowchart LR
    AI["AI client (OpenCode / Claude / any MCP host)"]
    SRV["FastMCP server (Python) safety · gating · Pydantic models"]
    BR["WebSocket listener ws://127.0.0.1:9080"]
    ADDON["Godot addon (GDScript) dials out · reconnects"]
    ED[("Live Godot project")]
    AI -->|"stdio (MCP)"| SRV
    SRV --- BR
    ADDON ==>|"connects out"| BR
    BR -.->|"{id, command, params}"| ADDON
    ADDON -->|"Editor API"| ED
    ADDON -.->|"{id, ok, result, error}"| BR
```

The bold arrow is the transport — the editor dials out and reconnects, so
launch order never matters. Once connected, the **server still initiates every
command**; the addon responds.

## The proof in one call

Ask the agent to create a node under an instanced scene child:

```text
> godot_scene_edit_create_node(parent_path="Relic/Cold", node_type="Node", name="Extra")

{ "node_path": "Relic/Cold/Extra", "created": true,
  "persisted": false,
  "reason": "instanced_child_not_editable",
  "hint": "'Relic/Cold' is inside the instanced scene 'Relic', which does not
           have Editable Children enabled — the change shows in the editor but
           will not be saved. Enable Editable Children on 'Relic', or target a
           node the scene owns." }

PROOF: a file-blind agent would believe the node was created. The verdict
names the failure AND the fix — and godot_scene_edit_set_editable_children
is the action the hint names.
```

Run it yourself: [getting started](./getting-started) — the whole surface is
additive and pinned by contract tests.

> [!WARNING]
> **Contract version 1** — clients negotiate via
> `godot_get_server_info`'s `contract_version` / `min_compatible_contract`.
> Additive changes never break a client; removals and renames bump the counter.

---

## Where to go next

- **[What & why](./what-why)** — the reasoning behind every major design decision
- **[Core concepts](./concepts)** — the five ideas the rest of the docs assume
- **[Architecture](./architecture/)** — the bridge, the envelope, gating, safety, persistence, readiness
- **[Reference](./reference)** — every tool, safety class, value shape, error code, env var
- **[Guides](./guides)** — build a scene, play-test and debug, verify your work