# godot-mcp Skills

godot-mcp ships four AI skills that give your agent expert knowledge when
building Godot games through the MCP tools. Two categories:

- **MCP workflow skills** — step-by-step recipes for calling the tools
  correctly (enable toolsets, build scenes, play-test and debug).
- **Engine knowledge skill** — Godot 4.x engine rules and common-bug
  prevention (rendering, physics, autoloads, GDScript gotchas).

Install them once and your agent has the right guidance at the right time.

---

## Install

### Prerequisites

- A clone of this repo
- An AI client that supports skills (opencode, Claude Code, etc.)

### One-command install

```bash
# opencode (default — symlinks into ~/.config/opencode/skills/):
./scripts/install-skills.sh

# Claude Code:
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
ln -s "$(pwd)/skills/godot-mcp-getting-started" ~/.config/opencode/skills/godot-mcp-getting-started
ln -s "$(pwd)/skills/godot-mcp-build-a-scene" ~/.config/opencode/skills/godot-mcp-build-a-scene
ln -s "$(pwd)/skills/godot-mcp-playtest-and-debug" ~/.config/opencode/skills/godot-mcp-playtest-and-debug
```

---

## Skills

### godot-mcp-getting-started

**Purpose:** Connect to and drive a Godot editor through the godot-mcp
server. Read this once at the start of any Godot session — it prevents the
two most common failures: missing tools (toolset not enabled) and
unconfirmed destructive edits.

**Triggers on:** "use godot-mcp", "drive Godot", "control the Godot
editor", "godot-mcp tools aren't showing up", "unknown tool from godot",
"set up godot-mcp".

**What it teaches:**
- Confirming the bridge is connected (Godot + addon running)
- The toolset-gating model (enable a toolset before its tools exist)
- The safety convention (read-only / mutating with `dry_run` / destructive
  with `confirm`)
- Using built-in workflow prompts (`/build_scene`, `/play_test`, etc.)
- Error recovery (`unknown tool`, `PRECONDITION_FAILED`, `BRIDGE_DISCONNECTED`)

**When to use:** First thing in any session that involves godot-mcp.

---

### godot-mcp-build-a-scene

**Purpose:** Step-by-step recipe for building or editing a Godot scene
through the MCP tools — create a scene, add and position nodes, attach
GDScript, add collision, then save and verify.

**Triggers on:** "build a Godot scene", "add a node in Godot", "create a
scene", "attach a script to a node", "set up a player scene", "edit the
scene tree".

**What it teaches:**
- Enabling the `scene_edit`, `scripts`, and `physics` toolsets
- Creating or opening a scene
- Adding and positioning nodes (parent paths, typed property values)
- Attaching GDScript to nodes
- Adding collision (CollisionShape2D + shape resources)
- Saving and verifying (scene tree + parse errors)
- Safety preview with `dry_run` and `confirm`

**When to use:** When scaffolding a new scene or modifying the node tree
of an existing one.

---

### godot-mcp-playtest-and-debug

**Purpose:** Run, inspect, and debug a live Godot game through the MCP
tools — play a scene, read the running scene tree, sample live properties,
simulate input, assert state, and diagnose errors.

**Triggers on:** "play-test in Godot", "run the game and check", "simulate
input in Godot", "why does my Godot game crash", "debug the running scene",
"inspect the live game".

**What it teaches:**
- Enabling the `runtime`, `input`, `testing`, and `debugger` toolsets
- Registering the runtime probe autoload
- Playing a scene and inspecting the live scene tree
- Simulating keyboard/mouse/action input
- Asserting live node state (property comparisons)
- Debugging failures (crash on play, parse errors, input does nothing)
- Using the debugger (breakpoints, stack frames, step-through)

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
"autoload not working", "scene file format".

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
parse.

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
  ├─ godot-mcp-getting-started activates    ← "how to connect to Godot"
  │   └─ agent enables toolsets, verifies bridge
  │
  ├─ godot-expert activates                  ← "how to build in Godot"
  │   └─ agent uses Polygon2D not ColorRect, checks z-order, etc.
  │
  ├─ godot-mcp-build-a-scene activates       ← "how to scaffold a scene"
  │   └─ agent creates scene, adds nodes, attaches scripts
  │
  └─ godot-mcp-playtest-and-debug activates  ← "how to test it"
      └─ agent plays the scene, inspects, simulates input
```

The workflow skills (`getting-started`, `build-a-scene`,
`playtest-and-debug`) teach **how to call the tools**. The engine skill
(`godot-expert`) teaches **why things break**. Use them together.

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
├── godot-mcp-getting-started/         # MCP workflow: bridge + toolsets + safety
│   └── SKILL.md                       # 46 lines
├── godot-mcp-build-a-scene/           # MCP workflow: scene scaffolding recipe
│   └── SKILL.md                       # 64 lines
├── godot-mcp-playtest-and-debug/      # MCP workflow: runtime + debug recipe
│   └── SKILL.md                       # 62 lines
└── godot-expert/                      # Engine knowledge: Godot 4.x expert rules
    ├── SKILL.md                       # 567 lines (10 sections)
    └── references/                    # 7 specialized guides
        ├── ui-hud.md                  # 170 lines
        ├── physics-collision.md       # 138 lines
        ├── testing-gut.md             # 203 lines
        ├── scene-authoring.md          # 173 lines
        ├── autoload-architecture.md   # 214 lines
        ├── scene-templates.md          # 123 lines
        └── common-bugs.md              # 238 lines
```