# Godot Editor MCP Skills

Godot Editor MCP ships three AI skills that give your agent expert knowledge when
building Godot games through the MCP tools. Two categories:

- **MCP workflow skills** — step-by-step recipes for calling the tools
  correctly (version + bridge check, enable toolsets, play-test and debug).
- **Engine knowledge skill** — Godot 4.x engine rules and common-bug
  prevention (rendering, physics, autoloads, GDScript gotchas, scene
  authoring).

The skills document the surface as of **2026.10.24**. `godot-getting-started`
teaches how to check the live server version (`godot_health_check`) — if the
server you're driving is older or newer, trust `godot_get_server_info()`'s
inventory over anything the skills state, and read the live counts from
`godot_get_server_info()` / `godot_list_toolsets()` rather than from prose here.

Alongside them, [`godot-rules.md`](godot-rules.md) is a one-page set of always-on
rules (paths, which tool for which change, "done means verified", GDScript 4.x
essentials). Put it in your agent's always-on instructions: skills load only when
the model decides to, and the rules cover what an agent gets wrong before it ever
reaches for one. See [Always-on rules](#always-on-rules-godot-rulesmd).

Install them once and your agent has the right guidance at the right time.

The companion **documentation site** is at https://hybridindie.github.io/godot-mcp/ — for
LLM agents, [`llms.txt`](https://hybridindie.github.io/godot-mcp/llms.txt) and
[`llms-full.txt`](https://hybridindie.github.io/godot-mcp/llms-full.txt) serve the same
docs in agent-friendly markdown.

---

## Install

### Prerequisites

- The Godot Editor MCP repo (clone or download)
- An AI client that supports skills (opencode, etc.)

### Copy the folders

```bash
git clone --depth 1 https://github.com/hybridindie/godot-mcp /tmp/godot-mcp
cd /tmp/godot-mcp/skills
cp -r godot-getting-started godot-playtest-and-debug godot-expert \
  ~/.config/opencode/skills/   # Claude: ~/.claude/skills/
```

Copy **all three** folders — `godot-getting-started/`, `godot-playtest-and-debug/`,
and `godot-expert/` — and keep `godot-expert/references/` intact: its 12 guides load
on demand. Then reload your skills.

### Verify

After installing, restart your AI client. The skills activate
automatically when their trigger conditions match (see below). You can
verify they're loaded by asking your agent about any of the trigger
topics.

### Copy, don't symlink

Install the skill folders as real copies. Some clients don't list files under a
symlinked skill directory (OpenCode shows an empty file list for it), so the
`references/` guides become invisible to the agent. Re-copy after you update the repo.

---

## Always-on rules (godot-rules.md)

[`godot-rules.md`](godot-rules.md) is short on purpose (one page, paid on every model
call). It covers what a coding agent with file tools gets wrong on a Godot project:

- `res://` is the project root on disk, so never hand a `res://` path to a file tool;
- scripts are edited directly and then parse-checked, while scenes and nodes change
  only through the MCP scene tools (the open editor overwrites hand-edited `.tscn`);
- enable a toolset before using its tools, and save the scene;
- read the result back before reporting success, and do only what was asked;
- GDScript 4.x and GUT essentials, and which skill to load for what.

Wire it into your client's always-on instructions:

| Client | How |
|---|---|
| OpenCode | `opencode.json`: `"instructions": ["path/to/godot-rules.md"]` |
| Claude Code | In the project's `CLAUDE.md`, import it on its own line: `@path/to/godot-rules.md` |
| Cursor | Save as `.cursor/rules/godot.mdc` with `alwaysApply: true` frontmatter |
| Anything else | Append it to the project's `AGENTS.md` or the client's system prompt / rules |

---

## Skills

### godot-getting-started

**Purpose:** Connect to and drive a Godot editor through the Godot Editor MCP
server. Read this once at the start of any Godot session — it prevents the
two most common failures: missing tools (toolset not enabled) and
unconfirmed destructive edits.

**Triggers on:** the start of any Godot task when the MCP tools are available:
"create a script", "add a node", "edit the scene", "set a property", "attach a
script". Also on "Godot Editor MCP tools aren't showing up" and "unknown tool from
godot".

**What it teaches:**
- Checking the server version + bridge connection (`godot_health_check`, `godot_get_server_info`)
- The toolset-gating model (enable a toolset before its tools exist; `godot_list_toolsets()` lists them all)
- The safety convention (read-only / mutating with `dry_run` / destructive
  with `confirm`)
- Using built-in workflow prompts (`/build_scene`, `/play_test`, `/author_resource`, `/export_build`, `/batch_refactor`, etc.)
- Error recovery (`unknown tool`, `PRECONDITION_FAILED`, `BRIDGE_DISCONNECTED`)

**When to use:** First thing in any session that involves Godot Editor MCP.

---

### godot-playtest-and-debug

**Purpose:** Run, inspect, and debug a live Godot game through the MCP
tools — play a scene, read the running scene tree, sample live properties,
simulate input, assert state, and diagnose errors.

**Triggers on:** "run the game and check", "does it work at runtime", "play-test
in Godot", "simulate input", "why does my Godot game crash", "debug the running
scene", "inspect the live game".

**What it teaches:**
- The two run modes: headless `run_and_capture` vs. the live play session with probe
- Enabling the `runtime`, `input`, `testing`, `debugger` (+ `profiling`) toolsets
- Registering the runtime probe autoload
- Playing a scene and inspecting the live scene tree; finding UI elements
- Simulating keyboard/mouse/action input; recording and replaying input macros
- Asserting live node state; scenarios, stress fuzz, screenshot diffing
- Debugging failures (crash on play, parse errors, input does nothing)
- The debugger: `force_break`, breakpoints, stepping (`step_into/over/out`), and
  in-game expression evaluation (`evaluate_expression`, not frame-scoped on 4.7)

**When to use:** When testing a running game, reproducing a bug, or
diagnosing runtime behavior.

---

### godot-expert

**Purpose:** Expert Godot 4.x engine knowledge for building games through
the MCP tools. Encodes every rule and pitfall an expert Godot developer
knows — learned the hard way by hitting each bug, debugging it, and writing
a test to pin it. Prevents the common failures: invisible sprites, input
blocked by overlays, enemies not spawning, parse errors, and more.

**Triggers on:** any Godot 4.x game work: "write a script", "add and configure
nodes", "build a scene", "UI/HUD", "collision setup", "autoload", "shader",
"animation", "write a GUT test". Also on bugs like "sprite not showing", "input not
working", "enemy not spawning" and "GDScript parse error".

**What it teaches:** a lean core (about 7.5 KB) that applies to all work, plus 12 guides
it tells the agent to read **before** each kind of work (#788):
- **Read before you build:** one "Before X, read `references/…`" line per guide (UI, physics,
  GUT, scene authoring, autoloads, templates, tilemaps, shaders, themes, animation, bugs)
1. **Node types & rendering:** Control vs Node2D, Polygon2D, draw order, spawn under the scene root
2. **Input & pause:** the overlay `mouse_filter` trap, custom WASD actions, `PROCESS_MODE_ALWAYS`
3. **Physics in one paragraph:** layer vs mask, the shape is a resource
4. **GDScript gotchas:** `:=` inference, signal renames, the 4.8 changes, `EditorDock` on 4.6+
5. **Scenes, saving & MCP tools:** MCP over hand edits, save/`persisted`, parse checks,
   `describe_class`, the honesty fields
6. **Checklist before you report done**

**Reference guides (loaded on demand):**

| File | Topic |
|------|-------|
| `references/ui-hud.md` | CanvasLayer vs Node2D, Control layout (anchors, presets, mouse_filter), full-screen overlay pattern, ProgressBar/Label/Button |
| `references/physics-collision.md` | Body types (CharacterBody2D vs Area2D vs StaticBody2D), collision layer/mask convention, CollisionShape2D resources, contact detection |
| `references/testing-gut.md` | GUT setup and install, test patterns (signals, groups, state machines), 6 gotchas, MCP `run_tests` tool |
| `references/scene-authoring.md` | .tscn format (ext_resource, sub_resource, node blocks), text vs GDScript syntax differences, disk vs bridge editing |
| `references/autoload-architecture.md` | Autoload registration and lifecycle, children-rendering trap, state persistence, state machine pattern, signal contracts, entity groups |
| `references/scene-templates.md` | Ready-to-use .tscn templates (player, enemy, projectile, main scene, WASD input actions) |
| `references/tileset-gridmap.md` | TileSet authoring (atlas source → create_tile → set_cell), GridMap + MeshLibrary authoring, atlas/grid pitfalls |
| `references/visual-shader.md` | VisualShader graph authoring (node ids, port-index wiring), text-vs-graph choice, read-back |
| `references/shader-authoring.md` | Text `.gdshader` authoring, `validate_shader` before assign, `shader_type` matching, params, persistence |
| `references/theme-styling.md` | Theme vs local override, item names, per-state styleboxes, color/size tools, override read-back |
| `references/particles-animation.md` | Particles (amount/lifetime/gradient), Animation tracks/keyframes + AnimationTree, Navigation region/bake/agent |
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

5. Any directory under `skills/` is picked up once copied into a client's skill
   directory — no registration needed.

## Repository structure

```
skills/
├── README.md                          # This file
├── godot-getting-started/             # MCP workflow: version + bridge + toolsets + safety
│   └── SKILL.md
├── godot-playtest-and-debug/          # MCP workflow: runtime + input + debugger recipe
│   └── SKILL.md
└── godot-expert/                      # Engine knowledge: Godot 4.x expert rules
    ├── SKILL.md                       # lean core + read-before pointers
    └── references/                    # 12 specialized guides
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