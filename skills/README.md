# godot-mcp Skills

Expert knowledge skills that ship with godot-mcp. Install them into your AI
client (opencode, Claude, etc.) so the agent has Godot expert guidance when
building games through the MCP tools.

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

### godot-expert

Expert Godot 4.x game development knowledge for building through the MCP tools.
Encodes the engine rules, node-type constraints, rendering order, autoload
lifecycle, and common bugs — every lesson learned the hard way.

**Reference guides:**

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
└── godot-expert/
    ├── SKILL.md              # Main skill (loaded by the client)
    └── references/           # Specialized guides (loaded on demand)
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