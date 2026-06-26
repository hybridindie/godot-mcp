# godot-mcp skills

Optional [Claude](https://claude.com/claude-code) **skills** that help an agent drive the godot-mcp server well. Unlike the server's MCP **prompts** (which a user invokes as slash commands), a skill auto-triggers when the agent recognizes a matching task from its `description` — so the guidance reaches the model without anyone typing a command. They are Claude-specific; other MCP clients should use the server's prompts instead.

These skills stay pure to the raw godot-mcp surface (toolsets, prompts, tools) — no game-specific or agent-workflow logic.

## Skills

| Skill | Use it for |
|-------|-----------|
| `godot-mcp-getting-started` | Connect/verify the bridge, the toolset-gating model, the `dry_run`/`confirm` safety convention |
| `godot-mcp-build-a-scene` | Scaffold/edit a scene: nodes, scripts, collision, save & verify |
| `godot-mcp-playtest-and-debug` | Play a live scene, inspect/sample, simulate input, assert, and diagnose errors |

## Install

Copy the skill directories to either location:

- **Personal (all projects):** `~/.claude/skills/`
- **Project (shared with a repo):** `<your-project>/.claude/skills/`

```bash
# from this repo root, into your personal skills dir
cp -R skills/godot-mcp-* ~/.claude/skills/
```

Each skill is a self-contained directory with a `SKILL.md`. After copying, the agent picks them up automatically; no MCP server change is required.

## Relationship to the server's prompts

Skills route to the same gated toolsets and the built-in workflow prompts (`build_scene`, `play_test`, `debug_scene`, `troubleshoot`, `author_resource`, `export_build`, `batch_refactor`, …). The prompts remain the canonical, client-agnostic recipes; the skills are the autonomous Claude front door.
