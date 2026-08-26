# godot-mcp Skills

Expert knowledge and workflow skills that ship with godot-mcp. Install them
into your AI client (opencode, Claude, etc.) so the agent has Godot expert
guidance when building games through the MCP tools.

## Install

```bash
# opencode (default — symlinks into ~/.config/opencode/skills/):
./scripts/install-skills.sh

# Claude:
./scripts/install-skills.sh --target ~/.claude/skills

# Copy instead of symlink (standalone, no repo dependency):
./scripts/install-skills.sh --copy
```

## Available skills

### MCP workflow skills (how to use the tools)

| Skill | Lines | When to use |
|-------|-------|------------|
| **godot-mcp-getting-started** | 46 | Start of any session — bridge connection, toolset gating, safety classes, error recovery |
| **godot-mcp-build-a-scene** | 64 | Building a scene — create/open, add nodes, attach scripts, add collision, save |
| **godot-mcp-playtest-and-debug** | 62 | Runtime testing — play, inspect live tree, simulate input, assert state, debug |

### Engine knowledge skills (why things break and how to avoid it)

| Skill | Lines | When to use |
|-------|-------|------------|
| **godot-expert** | 567 | Building or debugging a Godot game — node types, rendering, autoloads, physics, GDScript 4.7 gotchas, scene files, common bugs |

**The workflow skills teach *how to call the tools*. The engine skill teaches
*why things break*. Use them together.**

### godot-expert reference guides

| File | Topic |
|------|-------|
| `references/ui-hud.md` | CanvasLayer vs Node2D, Control layout, mouse_filter trap, overlay pattern |
| `references/physics-collision.md` | Body types, collision layers/masks, CollisionShape2D, contact detection |
| `references/testing-gut.md` | GUT setup, test patterns, gotchas, MCP run_tests tool |
| `references/scene-authoring.md` | .tscn format, ext/sub resources, disk vs bridge editing |
| `references/autoload-architecture.md` | Autoload lifecycle, children-rendering trap, state machines, signal contracts |
| `references/scene-templates.md` | Ready-to-use .tscn templates (player, enemy, projectile, main scene) |
| `references/common-bugs.md` | 11 documented bugs with symptom/root cause/fix |

## Structure

```
skills/
├── README.md
├── godot-mcp-getting-started/   # MCP workflow: bridge + toolsets + safety
│   └── SKILL.md
├── godot-mcp-build-a-scene/      # MCP workflow: scene scaffolding recipe
│   └── SKILL.md
├── godot-mcp-playtest-and-debug/ # MCP workflow: runtime + debug recipe
│   └── SKILL.md
└── godot-expert/                 # Engine knowledge: Godot 4.x expert rules
    ├── SKILL.md
    └── references/
        ├── ui-hud.md
        ├── physics-collision.md
        ├── testing-gut.md
        ├── scene-authoring.md
        ├── autoload-architecture.md
        ├── scene-templates.md
        └── common-bugs.md
```

Each skill has a YAML frontmatter (`name`, `description`) that tells the
client when to activate it. The client loads `SKILL.md` into context when
the skill triggers, and the agent reads reference files as needed.