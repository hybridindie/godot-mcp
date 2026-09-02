# godot-mcp Skills

godot-mcp ships three AI skills that give your agent expert knowledge when
building Godot games through the MCP tools. Two categories:

- **MCP workflow skills** — step-by-step recipes for calling the tools
  correctly (version + bridge check, enable toolsets, play-test and debug).
- **Engine knowledge skill** — Godot 4.x engine rules and common-bug
  prevention (rendering, physics, autoloads, GDScript gotchas, scene
  authoring).

The skills document the surface as of **2026.09.02** (180 tools across
29 categories, 9 workflow prompts). `godot-getting-started` teaches how to
check the live server version (`godot_health_check`) — if the server you're
driving is older or newer, trust `godot_get_server_info()`'s inventory over
the counts here.

Install them once and your agent has the right guidance at the right time.

---

## Install

### Prerequisites

- A clone of this repo
- An AI client that supports skills (opencode, etc.)

### One-command install

```bash
# opencode (default — symlinks into ~/.config/opencode/skills/):
./scripts/install-skills.sh

# Claude / other clients:
./scripts/install-skills.sh --target ~/.claude/skills

# Any client with a custom skill path:
./scripts/install-skills.sh --target /path/to/your/skills

# Copy instead of symlink (standalone — no repo dependency):
./scripts/install-skills.sh --copy

# See all options:
./scripts/install-skills.sh --help
```

**Symlink (default)** is recommended during development — updates to this
repo flow through automatically. Use `--copy` for a standalone install
(e.g. packaging a release).

### Verify

After installing, restart your AI client. The skills activate
automatically when their trigger conditions match (see below). You can
verify they're loaded by asking your agent about any of the trigger
topics.

### Manual install (no script)

If you prefer not to use the script:

```bash
# opencode:
ln -s "$(pwd)/skills/godot-expert" ~/.config/opencode/skills/godot-expert
ln -s "$(pwd)/skills/godot-getting-started" ~/.config/opencode/skills/godot-getting-started
ln -s "$(pwd)/skills/godot-playtest-and-debug" ~/.config/opencode/skills/godot-playtest-and-debug
```

---

## Skills

### godot-getting-started

**Purpose:** Connect to and drive a Godot editor through the godot-mcp
server. Read this once at the start of any Godot session — it prevents the
two most common failures: missing tools (toolset not enabled) and
unconfirmed destructive edits.

**Triggers on:** "use godot-mcp", "drive Godot", "control the Godot
editor", "godot-mcp tools aren't showing up", "unknown tool from godot",
"set up godot-mcp".

**What it teaches:**
- Checking the server version + bridge connection (`godot_health_check`, `godot_get_server_info`)
- The toolset-gating model (enable a toolset before its tools exist — 28 gated toolsets)
- The safety convention (read-only / mutating with `dry_run` / destructive
  with `confirm`)
- Using built-in workflow prompts (`/build_scene`, `/play_test`, `/author_resource`, `/export_build`, `/batch_refactor`, etc.)
- Error recovery (`unknown tool`, `PRECONDITION_FAILED`, `BRIDGE_DISCONNECTED`)

**When to use:** First thing in any session that involves godot-mcp.

---

### godot-playtest-and-debug

**Purpose:** Run, inspect, and debug a live Godot game through the MCP
tools — play a scene, read the running scene tree, sample live properties,
simulate input, assert state, and diagnose errors.

**Triggers on:** "play-test in Godot", "run the game and check", "simulate
input in Godot", "why does my Godot game crash", "debug the running scene",
"inspect the live game".

**What it teaches:**
- The two run modes: headless `run_and_capture` vs. the live play session with probe
- Enabling the `runtime`, `input`, `testing`, `debugger` (+ `profiling`) toolsets
- Registering the runtime probe autoload
- Playing a scene and inspecting the live scene tree; finding UI elements
- Simulating keyboard/mouse/action input; recording and replaying input macros
- Asserting live node state; scenarios, stress fuzz, screenshot diffing
- Debugging failures (crash on play, parse errors, input does nothing)
- The debugger: `force_break`, breakpoints, stack frames, frame variables,
  stepping (`step_into/over/out`), expression evaluation, continue

**When to use:** When testing a running game, reproducing a bug, or
diagnosing runtime behavior.

---

### godot-expert

**Purpose:** Expert Godot 4.x engine knowledge for building games through
the MCP tools. Encodes every rule and pitfall an expert Godot developer
knows — learned the hard way by hitting each bug, debugging it, and writing
a test to pin it. Prevents the common failures: invisible sprites, input
blocked by overlays, enemies not spawning, parse errors, and more.

**Triggers on:** "build a Godot game", "sprite not showing", "input not
working", "enemy not spawning", "GDScript parse error", "collision setup",
"autoload not working", "scene file format", "build a scene", "create a
scene", "attach a script".

**What it teaches (10 sections):**
1. **Node types & rendering** — Control vs Node2D, Polygon2D for
   no-asset shapes, z-ordering in the scene tree
2. **Autoloads & entity spawning** — the autoload-children rendering trap,
   state persistence across scene reloads
3. **Input handling** — the UI-overlay input trap (`mouse_filter`),
   custom WASD input actions, pause/process mode
4. **Collision layers & masks** — bitmask convention table, layer/mask
   values per entity, CollisionShape2D resources
5. **GDScript 4.7 type inference** — the `:=` trap, `PackedVector2Array`
   constructor, signal rename breakage
6. **Scene file format (.tscn)** — ext_resource, sub_resource, node
   blocks, text vs GDScript syntax, disk vs bridge editing
7. **Infinite background grids** — dynamic tile pool sized from viewport
8. **MCP bridge workflow** — starting the bridge, sending commands, common
   commands table
9. **Testing with GUT** — setup, test patterns, gotchas (no await ready,
   no `assert_contains`, autoload state leak), MCP `run_tests` tool
10. **Quick checklist** — verify before playing a scene

**Reference guides (loaded on demand):**

| File | Topic |
|------|-------|
| `references/ui-hud.md` | CanvasLayer vs Node2D, Control layout (anchors, presets, mouse_filter), full-screen overlay pattern, ProgressBar/Label/Button |
| `references/physics-collision.md` | Body types (CharacterBody2D vs Area2D vs StaticBody2D), collision layer/mask convention, CollisionShape2D resources, contact detection |
| `references/testing-gut.md` | GUT setup and install, test patterns (signals, groups, state machines), 6 gotchas, MCP `run_tests` tool |
| `references/scene-authoring.md` | .tscn format (ext_resource, sub_resource, node blocks), text vs GDScript syntax differences, disk vs bridge editing |
| `references/autoload-architecture.md` | Autoload registration and lifecycle, children-rendering trap, state persistence, state machine pattern, signal contracts, entity groups |
| `references/scene-templates.md` | Ready-to-use .tscn templates (player, enemy, projectile, main scene, WASD input actions) |
| `references/common-bugs.md` | 11 documented bugs with symptom/root cause/fix — each from real development |

**When to use:** Whenever building or debugging a Godot game — especially
when something isn't rendering, input isn't working, or a script won't
parse. Also covers scene scaffolding (create scene, add nodes, attach
scripts, add collision, save and verify).

---

## How skills work

Each skill is a directory with a `SKILL.md` file containing YAML
frontmatter:

```yaml
---
name: godot-expert
description: "Use when building or modifying a Godot 4.x game..."
---
```

The `description` field tells the AI client **when to activate** the skill.
When the trigger conditions match (e.g., the user mentions "sprite not
showing"), the client loads `SKILL.md` into the agent's context. The agent
then reads reference files from `references/` as needed.

Skills are **read-only knowledge** — they don't execute code or call tools.
They guide the agent's decisions when it uses the MCP tools.

## How the skills relate

```
User: "Build a survivors game in Godot"
  │
  ├─ godot-getting-started activates          ← "how to connect to Godot"
  │   └─ agent enables toolsets, verifies bridge
  │
  ├─ godot-expert activates                    ← "how to build in Godot"
  │   └─ agent uses Polygon2D not ColorRect, checks z-order, etc.
  │
  └─ godot-playtest-and-debug activates         ← "how to test it"
      └─ agent plays the scene, inspects, simulates input
```

The workflow skills (`getting-started`, `playtest-and-debug`) teach
**how to call the tools**. The engine skill (`godot-expert`) teaches
**why things break**. Use them together.

## Creating new skills

1. Create a directory under `skills/`:
   ```bash
   mkdir -p skills/my-new-skill
   ```

2. Write `SKILL.md` with frontmatter:
   ```markdown
   ---
   name: my-new-skill
   description: "Use when [trigger conditions]. [What it teaches]."
   ---

   # My New Skill

   ...
   ```

3. (Optional) Add reference files under `references/`:
   ```bash
   mkdir -p skills/my-new-skill/references
   ```

4. Update `skills/README.md` to document the new skill.

5. The install script (`scripts/install-skills.sh`) auto-discovers any
   directory under `skills/` — no registration needed.

## Repository structure

```
skills/
├── README.md                          # This file
├── godot-getting-started/             # MCP workflow: version + bridge + toolsets + safety
│   └── SKILL.md
├── godot-playtest-and-debug/          # MCP workflow: runtime + input + debugger recipe
│   └── SKILL.md
└── godot-expert/                      # Engine knowledge: Godot 4.x expert rules
    ├── SKILL.md                       # 10 sections
    └── references/                    # 7 specialized guides
        ├── ui-hud.md
        ├── physics-collision.md
        ├── testing-gut.md
        ├── scene-authoring.md
        ├── autoload-architecture.md
        ├── scene-templates.md
        └── common-bugs.md
```

The skills are pinned to the server surface by
`tests/unit/test_skills_metadata.py`: every `godot_*()` call a skill teaches
must resolve to a registered tool, the prompt lists must cover every registered
prompt, and the getting-started map must cover every toolset. A version bump
that changes the surface fails the suite until the skills catch up.