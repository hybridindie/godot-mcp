# Agent Ecosystem Research: Godot MCP Multi-Agent Orchestrator

> **Status**: Research & Planning Document  
> **Scope**: External product layer that consumes the open-source `godot-mcp` server.  
> **License**: This document and the planned agent product are proprietary. The underlying `godot-mcp` server and Godot addon remain MIT open-source.  

---

## 1. Executive Summary

This document captures comprehensive research into building a **multi-agent AI orchestration system** for Godot game development, inspired by and benchmarked against **Nwiro Pro** (Leartes Studios), a UE5-native MCP tool suite. The goal is to define an external product layer — distinct from the open-source `godot-mcp` engine bridge — that provides:

- **Multi-agent collaboration**: Specialized AI agents (Scene Architect, Script Engineer, Runtime Operator, Asset Curator) working in concert over a shared MCP bridge.
- **Local-first BYOK deployment**: Docker Compose stack where developers bring their own API keys (Anthropic, OpenAI, Meshy, Tripo).
- **Pro / Hosted tier**: Gated advanced pipelines (text-to-3D, team collaboration, cloud builds) delivered via subscription or credits.

The `godot-mcp` repository remains strictly game-agnostic and open-source. This agent product consumes it as a dependency, layering game-type awareness, orchestration, and advanced AI content generation on top.

---

## 2. Nwiro Pro Deep Analysis

### 2.1 What Nwiro Pro Is

Nwiro Pro is a commercial Unreal Engine 5 plugin that exposes ~200 native C++ MCP tools to Claude/GPT/Codex CLI. It enables AI agents to:

- Create and edit Blueprints (30+ node types), Materials, and C++ classes.
- Spawn, transform, and manage Actors in the world.
- Control Play-in-Editor (PIE) runtime: teleport, AI commands, blackboard manipulation.
- Edit Animation Montages, AnimBPs, State Machines, Sequencer tracks.
- Set breakpoints, watch values, compile-error analysis, auto-fix.
- Track asset dependencies, references, and orphans.
- Integrate external AI: Meshy AI (text-to-3D), Tripo AI (text/image-to-3D).
- Generate advanced PCG biomes from text prompts.

**Key insight**: Nwiro appears monolithic (200+ tools) but is actually a **dense API surface** over UE5's highly reflective C++ UObject system. Every tool is a native MCP endpoint — no Python or Node.js bridges.

### 2.2 Nwiro Pricing Model

| Tier | Price | What's Included |
|------|-------|-----------------|
| **Nwiro AI Integration Kit** | Perpetual License | Blueprint/Material/UI generation, AI bug fixing, zero dependency, Meshy/Tripo connection. NO advanced PCG, NO advanced Blueprint logic. |
| **Nwiro AI Pro** | Subscription or Credits | Everything in Kit + Advanced PCG Graph Generation, Advanced Blueprint Logic, Advanced Custom Plugin Architecture, Discord Support, multi-model access (Claude Opus 4.6, GPT-5.4, Gemini 3.1 Pro, DeepSeek V3.2, etc.). |

**BYOK Pattern**: Users sign in to Claude CLI or Codex CLI locally. No API keys are handled by Nwiro's servers. Project data never leaves the local machine for the Integration Kit tier.

### 2.3 Nwiro's Strengths We Should Emulate

1. **Native speed**: No Python/Node bridges — tools are C++ endpoints. Our equivalent is the GDScript addon calling Godot Editor API directly, which is comparably fast.
2. **Debugger integration**: The BP Debugger is Nwiro's "magic" feature. True breakpoint/step/watch inside the engine is the #1 gap for us.
3. **Macro shortcuts**: 4 built-in macros for common setups (basic level, light rig, grid/ring layout). These save massive token counts for agents.
4. **External AI integration**: Meshy and Tripo plugged directly into the Content Browser. We need a generic `import_asset` bridge.
5. **Zero-config setup**: Install plugin, log in to Claude CLI once, done. Our setup is already close (`uv run godot-mcp`, enable addon, configure client).

### 2.4 Nwiro's Weaknesses / Godot Advantages

1. **Godot is script-first**: UE5's Blueprint/C++ duality creates complexity. Godot's GDScript is the primary language — simpler for agents.
2. **Scene tree is the single abstraction**: No separate Actor/Component/Pawn hierarchy. One scene tree, one composition model.
3. **Smaller, more focused API**: Godot's editor API is less sprawling than UE5's UObject reflection. Easier to cover comprehensively.
4. **Open source core**: Our MCP server and addon are MIT. Nwiro is closed source. Community can extend.

---

## 3. Capability Gap Matrix

| Nwiro Category | Nwiro Tools | Godot Equivalent | `godot-mcp` Status | Gap for Agents |
|---|---|---|---|---|
| **Blueprints** | 18 | GDScript (primary); VS deprecated | **Complete** — 121 tools, strong coverage | None |
| **Materials** | 12 | ShaderMaterial, VisualShader | Partial — text shader tools exist | **No Visual Shader node-graph editing** |
| **World / Actors** | 17 | Scene tree composition | **Complete** — `scene_edit`, `scene_3d` | None |
| **PIE Runtime** | 14 | Editor play session + probe | **Complete** — `runtime`, `input`, `testing` | None |
| **Animation** | 9 | AnimationPlayer, AnimationTree | **Complete** — `animation` | Minor: blend trees, root motion |
| **Sequencer** | 6 | No native equivalent | Out of scope | N/A |
| **BP Debugger** | 10 | Script debugger | **Missing entirely** | **Critical gap** |
| **Asset Dependency** | 5 | No built-in referencers UI | **Missing** | **High** |
| **Enhanced Input** | 5 | Input Map + Events | **Complete** — `input_map` | Minor: contexts/modifiers |
| **Generic Asset** | 3 | ResourceLoader reflection | Partial | No universal property editor |
| **Data Structures** | 6 | Custom Resources, Arrays, Dictionaries | Partial | No native struct/enum (Godot limitation) |
| **Behavior Trees** | 7 | No native BT | Requires addon | Out of scope for core |
| **Widget / UMG** | 17 | Control nodes / Theme | **Complete** — `theme_ui` | Minor: visual layout drag-drop |
| **Niagara VFX** | 4 | GPUParticles3D/2D | **Complete** — `particles` | Minor: particle graph editing |
| **State Trees** | 3 | AnimationNodeStateMachine | Partial — `animation` | Minor gap |
| **IK Rigs** | 5 | SkeletonIK3D, BoneAttachment | Missing | Not planned |
| **Motion Matching** | 4 | No native equivalent | Missing | Out of scope |
| **Environment** | 5 | WorldEnvironment, Fog, Sky | Partial — `scene_3d` | **Post-process stack presets** |
| **Physics** | 4 | Body / Area / Collision | **Complete** — `physics` | None |
| **Spline** | 7 | Path2D/3D + Curve2D/3D | **Missing** | Medium |
| **Navigation** | 3 | Region / Agent / Mesh | **Complete** — `navigation` | None |
| **Audio** | 3 | Bus / Player / Effects | **Complete** — `audio` | None |
| **Game Framework** | 8 | Autoloads / scene composition | Partial — `register_autoload` | **Project template scaffolding** |
| **GAS** | 6 | No native equivalent | Requires addon | Out of scope |
| **PCG** | 4 | No native equivalent | Requires addon | **Major gap** |
| **Level** | 5 | Scene files + instances | **Complete** — `scene_edit` | None |
| **Landscape** | 3 | No native terrain | Requires addon | **Major gap** |
| **Foliage** | 4 | No native foliage | Requires addon | **Major gap** |
| **Networking** | 3 | Multiplayer API | Missing | Minor gap |
| **World Partition** | 2 | No native equivalent | Missing | Out of scope |
| **Macro Shortcuts** | 4 | None built-in | **Missing** | **High** |
| **Build / Validation** | 5 | Godot CLI | **Complete** — `export`, `analysis` | Good parity |
| **Editor** | 4 | EditorInterface | **Complete** — `editor` | Good parity |
| **File Operations** | 4 | OS file API | **Complete** — `project` | Good parity |
| **AI Content (Meshy/Tripo)** | — | External APIs | **Missing** | **High** |
| **Advanced Biome Gen** | — | No native equivalent | **Missing** | **High** |

### 3.1 Gap Severity Classification

| Severity | Count | Categories |
|---|---|---|
| **Critical** | 2 | Debugger, Asset Dependency |
| **High** | 6 | Visual Shader, Macro Shortcuts, Project Scaffolding, AI Content Import, Orphan Detection, Post-Process |
| **Medium** | 4 | Spline, Advanced Animation, UI Layout, Particle Graph |
| **Low / Minor** | 5 | Enhanced Input Contexts, Networking, Generic Asset Editor, Data Structs, Foliage |
| **Out of Scope** | 8 | Sequencer, Behavior Trees, IK, Motion Matching, GAS, PCG, Landscape, World Partition |

---

## 4. Multi-Agent Graph Architecture

### 4.1 Why Multi-Agent?

Nwiro is monolithic: one agent with 200+ tools. For Godot, a **multi-agent graph** is superior because:

1. **Context window efficiency**: Each agent loads 20-30 relevant tools instead of 200.
2. **Specialized prompting**: The Script Engineer speaks GDScript idioms; the Scene Architect knows composition patterns.
3. **Parallel work**: Scene Architect builds the level while Script Engineer writes the player controller.
4. **Retry isolation**: Script failure doesn't lose the Scene Architect's progress.
5. **Team simulation**: Mirrors how real studios work — designers design, programmers program, testers test.

### 4.2 Agent Graph

```
┌─────────────────────────────────────────────────────────────────┐
│                        Orchestrator Agent                         │
│  (Natural language → plan → DAG → delegates to specialists)       │
│  Toolsets: core, project, planning                                │
└──────────┬─────────────┬─────────────┬─────────────┬────────────┘
           │             │             │             │
    _______▼_____  _____▼_____   _____▼_____   _____▼_____
   ║  Scene      ║║ Script    ║║ Runtime   ║║ Asset     ║
   ║  Architect  ║║ Engineer  ║║ Operator  ║║ Curator   ║
   ╚═════════════╝╚═══════════╝╚═══════════╝╚═══════════╝
        │            │            │            │
        ▼            ▼            ▼            ▼
   [scene_edit]   [scripts]    [runtime]    [resources]
   [scene_3d]     [analysis]   [testing]    [project]
   [tilemap]      [input_map]  [profiling]  [export]
   [physics]      [batch]      [input]      [import_asset]
   [animation]    [macro_scaffold]          [dependencies]
   [particles]                              [visual_shader]
   [theme_ui]                               [spline]
   [shaders]
```

### 4.3 Agent Specifications

#### Orchestrator Agent
- **Role**: Session manager, planner, delegator, conflict resolver.
- **Input**: User natural language prompt (e.g., "Build a 2D platformer where the player collects coins and avoids spikes").
- **Output**: JSON DAG of `AgentTask` objects with `depends_on` edges.
- **State**: Shared project state store (SQLite / JSONL / Redis) that all agents read/write.
- **Safety**: Detects when two agents target the same scene/script and serializes access via soft locks.
- **Model**: Claude 3.5 Sonnet / GPT-4o class (good at planning, not necessarily the largest model).

#### Scene Architect
- **Role**: Builds levels, places nodes, configures transforms, lighting, camera, physics.
- **Expertise**: Godot node hierarchy, scene composition, visual design patterns, TileMap, GridMap, 3D environment setup.
- **Enabled Toolsets**: `scene_edit`, `scene_3d`, `physics`, `animation`, `particles`, `theme_ui`, `shaders`, `tilemap`, `visual_shader`, `spline`, `macro_scaffold`.
- **Typical Workflow**:
  1. `get_active_scene` → `get_scene_tree` (discovery)
  2. `macro_create_player_2d` or `macro_create_camera_rig` (scaffold)
  3. `create_node` / `set_node_property` for custom placements
  4. `save_scene` / `capture_editor_screenshot` (verification)
- **Model**: Claude 3.5 Sonnet (fast, good at spatial reasoning).

#### Script Engineer
- **Role**: Writes, edits, and validates GDScript; connects signals; configures input; designs game systems (state machines, health, inventory, dialogue).
- **Expertise**: GDScript idioms, Godot signals/groups, Input Map patterns, autoload architecture.
- **Enabled Toolsets**: `scripts`, `input_map`, `analysis`, `batch`, `macro_scaffold` (script portion only).
- **Typical Workflow**:
  1. `read_script` (understand existing code)
  2. `write_script` or `patch_script` (implement feature)
  3. `get_parse_errors` (validate)
  4. `connect_signal` (wire to scene)
  5. `debug_workflow` (comprehensive check)
- **Model**: Claude 3.5 Sonnet / GPT-4o (excellent at code generation).

#### Runtime Operator
- **Role**: Plays the game, runs tests, captures screenshots, profiles performance, manages debug sessions.
- **Expertise**: Play-test loops, assertion evaluation, performance monitor interpretation, screenshot diffing.
- **Enabled Toolsets**: `runtime`, `testing`, `profiling`, `input`, `export`, `editor`.
- **Typical Workflow**:
  1. `play_scene` (launch)
  2. `get_game_scene_tree` / `simulate_action` (drive)
  3. `assert_node_state` / `compare_screenshots` (verify)
  4. `get_performance_monitors` / `record_input` (diagnostics)
  5. `stop_scene` / `export_project` (wrap-up)
- **Model**: Claude 3.5 Haiku / GPT-4o Mini (fast, cheap, good at structured evaluation).

#### Asset Curator
- **Role**: Imports external assets, validates integrity, tracks dependencies, manages orphaned resources, assembles materials.
- **Expertise**: Godot import pipeline, resource dependencies, PBR material assembly, external AI APIs (Pro tier).
- **Enabled Toolsets**: `resources`, `project`, `dependencies`, `import_asset`, `batch` (refactor), `visual_shader`.
- **Typical Workflow**:
  1. `import_asset` (drop in external file or AI-generated content)
  2. `create_material_from_textures` (assemble PBR material)
  3. `analyze_dependencies` (validate nothing is broken)
  4. `find_orphaned_resources` (cleanup)
- **Model**: Claude 3.5 Sonnet (good at structured data handling).

---

## 5. Inter-Agent Communication Protocol

### 5.1 Shared State Store

Append-only JSONL file in `.agent/session_state.jsonl` (gitignored):

```json
{"ts":"2026-06-08T12:00:00Z","agent":"orchestrator","event":"plan_created","plan_id":"plan_001","tasks":["scene_init","player_script","playtest_v1"]}
{"ts":"2026-06-08T12:01:00Z","agent":"scene_architect","event":"task_started","task_id":"scene_init"}
{"ts":"2026-06-08T12:02:00Z","agent":"scene_architect","event":"task_completed","task_id":"scene_init","outputs":{"scene_path":"res://main.tscn","nodes_created":["Player","Camera2D"]}}
{"ts":"2026-06-08T12:03:00Z","agent":"script_engineer","event":"task_started","task_id":"player_script","inputs":{"scene_path":"res://main.tscn","player_node":"Player"}}
```

**Why JSONL**: Human-readable, append-only (no locks needed for writes), easy to tail, trivial to parse line-by-line.

### 5.2 Conflict Resolution

Before any mutating tool call, an agent **must** acquire a soft lock:

```json
{
  "agent_id": "scene_architect",
  "resource": "res://main.tscn",
  "acquired_at": "2026-06-08T12:01:00Z",
  "expires_at": "2026-06-08T12:06:00Z"
}
```

- Held locks are visible in shared state.
- Orchestrator arbitrates timeouts (auto-expire after 5 minutes) and deadlocks (cycle detection in lock graph).
- Agents can `release_lock(resource)` explicitly on completion.

### 5.3 Agent Message Bus

Lightweight pub/sub using Redis (local Docker) or file watchers:

```json
{
  "from": "script_engineer",
  "to": "scene_architect",
  "type": "request",
  "topic": "add_child_node",
  "payload": {
    "parent_path": "Player",
    "node_type": "StateMachine",
    "node_name": "MovementFSM"
  },
  "correlation_id": "msg_042"
}
```

Response:

```json
{
  "from": "scene_architect",
  "to": "script_engineer",
  "type": "response",
  "correlation_id": "msg_042",
  "status": "completed",
  "outputs": {
    "node_path": "./Player/MovementFSM"
  }
}
```

---

## 6. Orchestrator Schema

```python
class OrchestratorPlan(BaseModel):
    version: str = "1.0"
    plan_id: str  # uuid
    project_path: str  # res://
    tasks: list[AgentTask]

class AgentTask(BaseModel):
    task_id: str  # uuid
    agent_id: Literal["scene_architect", "script_engineer", "runtime_operator", "asset_curator"]
    toolsets: list[str]  # toolset names to enable
    instructions: str  # Natural language goal
    depends_on: list[str]  # task_ids that must complete first
    outputs: list[str]  # Expected artifacts (node_paths, script_paths, etc.)
    max_retries: int = 3
    timeout_seconds: int = 300
```

**DAG Execution**: Topological sort of `depends_on` edges. Parallel tasks with no interdependency run concurrently. The Orchestrator polls `session_state.jsonl` for task completion events.

---

## 7. Local BYOK Docker Compose Stack

### 7.1 Services

```yaml
# docker-compose.yml (agent product repo)
services:
  mcp-server:
    image: ghcr.io/hybridindie/godot-mcp:latest
    environment:
      GODOT_MCP_TRANSPORT: http
      GODOT_MCP_HTTP_HOST: 0.0.0.0
      GODOT_MCP_HTTP_PORT: 9090
      GODOT_MCP_BRIDGE_URL: ws://host.docker.internal:9080
    ports:
      - "9090:9090"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9090/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  agent-orchestrator:
    build: ./agent_orchestrator
    environment:
      MCP_SERVER_URL: http://mcp-server:9090
      REDIS_URL: redis://state-store:6379
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    depends_on:
      - mcp-server
      - state-store
    volumes:
      - ${GODOT_PROJECT_PATH}:/project:rw

  state-store:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

  web-ui:
    build: ./web_ui
    ports:
      - "3000:3000"
    environment:
      ORCHESTRATOR_URL: http://agent-orchestrator:8000
    depends_on:
      - agent-orchestrator

volumes:
  redis_data:
```

### 7.2 BYOK Configuration

Users create `.env`:

```bash
# .env (never committed)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
MESHY_API_KEY=msy-...
TRIPO_API_KEY=tp-...
GODOT_PROJECT_PATH=/Users/dev/my_godot_game
```

### 7.3 Networking

- `mcp-server` exposes HTTP on `0.0.0.0:9090` (MCP transport for all agents).
- `agent-orchestrator` connects to MCP server + Redis. Manages agent lifecycle.
- Godot editor on the **host** machine connects its addon to `ws://host.docker.internal:9080`.
- `web-ui` provides a local dashboard for monitoring agent progress, logs, and screenshots.

### 7.4 Why Docker?

- **Isolation**: Python/Node dependencies don't pollute the host.
- **Reproducibility**: Same stack for every developer.
- **CI Ready**: The compose file works in GitHub Actions for automated testing.
- **Upgrade path**: Swap `ghcr.io/hybridindie/godot-mcp:latest` for a pinned version.

---

## 8. Pro / Hosted Feature Gating

### 8.1 Feature Matrix

| Feature | Local (BYOK Free) | Pro (Hosted / Subscription) |
|---|---|---|
| Multi-agent graph (4 agents) | ✅ | ✅ |
| Generic macro scaffolds | ✅ | ✅ |
| GDScript editing & validation | ✅ | ✅ |
| Scene editing & runtime testing | ✅ | ✅ |
| Asset dependency tracking | ✅ | ✅ |
| Visual Shader / Spline tools | ✅ | ✅ |
| Docker Compose packaging | ✅ | ✅ |
| **Text-to-3D (Meshy/Tripo)** | ❌ (no API keys) | ✅ (billed via credits) |
| **AI texture generation** | ❌ | ✅ |
| **AI audio/SFX generation** | ❌ | ✅ |
| **Team collaboration / merging** | ❌ | ✅ |
| **Cloud build / CI export** | ❌ | ✅ |
| **Pre-trained game-type agents** | ❌ | ✅ |
| **Priority model access (Claude Opus)** | ❌ | ✅ |
| **Advanced PCG / biome generation** | ❌ | ✅ |
| **Landscape / foliage generation** | ❌ | ✅ |

### 8.2 Gating Mechanism

Pro features are not "disabled code" in the local version — they are **agents/toolsets that require hosted API endpoints**:

- **Text-to-3D**: Local version has no Meshy/Tripo key. Pro version proxies through our server which holds pooled API keys and bills per generation.
- **Team collaboration**: Local state is SQLite on disk. Pro uses cloud PostgreSQL with real-time sync.
- **Cloud build**: Local export uses the user's Godot binary. Pro spins up ephemeral cloud runners.

**No license keys, no DRM in the local stack.** The open-source nature of `godot-mcp` makes DRM impossible anyway. Gating is purely **service-based**.

### 8.3 Pricing Hypothesis

| Tier | Price Point | Target |
|---|---|---|
| **Free / BYOK** | $0 | Solo developers, hobbyists, students. Bring your own Claude/OpenAI API key. |
| **Pro** | $29-49/mo or credit packs | Indie studios, small teams. Access to all AI models, cloud builds, team features. |
| **Studio** | Custom / seat-based | AAA-adjacent studios. Custom agents, SLA, private cloud, training on proprietary assets. |

---

## 9. Dependency on `godot-mcp`

This agent product is a **consumer**, not a fork, of the open-source `godot-mcp` server.

### 9.1 Integration Contract

```yaml
# docker-compose.yml (excerpt)
services:
  mcp-server:
    image: ghcr.io/hybridindie/godot-mcp:${GODOT_MCP_VERSION:-latest}
    environment:
      GODOT_MCP_TRANSPORT: http
      GODOT_MCP_HTTP_PORT: 9090
      GODOT_MCP_BRIDGE_URL: ws://host.docker.internal:9080
```

### 9.2 Compatibility Matrix

| Agent Product Version | godot-mcp Version | Notes |
|---|---|---|
| 0.1.0-alpha | >= 1.0.0 | Requires macros, project_scaffold, visual_shader toolsets |
| 0.2.0-beta | >= 1.1.0 | Requires debugger toolset (if go from spike) |
| 1.0.0-stable | >= 1.2.0 | Full surface parity with Nwiro Pro Integration Kit |
| 1.1.0-pro | >= 1.3.0 | Requires import_asset, AI content pipelines |

### 9.3 Upgrade Policy

- `godot-mcp` releases follow CalVer (per `.claude/rules/enforcement.md`).
- The agent product pins a minimum `godot-mcp` version and validates on startup.
- New MCP toolsets are adopted incrementally; the agent product doesn't need to upgrade immediately.

---

## 10. Roadmap

### Phase 1: Foundation (Weeks 1-3)
**Goal**: Working local stack with Orchestrator + 2 agents.

- [ ] Agent orchestrator service (FastAPI / Python)
- [ ] Shared state store (SQLite v1)
- [ ] Scene Architect agent (prompts + tool selection)
- [ ] Script Engineer agent (prompts + tool selection)
- [ ] Basic DAG execution (topological sort + sequential execution)
- [ ] Docker Compose packaging
- [ ] Integration with `godot-mcp` >= 1.0.0

**Deliverable**: `docker compose up` → "Create a 2D platformer player" → Scene Architect builds node tree, Script Engineer writes GDScript.

### Phase 2: Full Quartet (Weeks 4-6)
**Goal**: All 4 agents operational + runtime loop.

- [ ] Runtime Operator agent (play-test loop, assertions)
- [ ] Asset Curator agent (import, dependency tracking)
- [ ] Conflict resolution (soft locks, deadlock detection)
- [ ] Retry and error recovery (agent replanning on failure)
- [ ] Web UI dashboard (agent status, logs, screenshots)

**Deliverable**: End-to-end "Build, test, fix" loop without human intervention.

### Phase 3: AI Content Pipelines (Weeks 7-10)
**Goal**: Hosted Pro features — text-to-3D, AI textures, team sync.

- [ ] Meshy AI proxy integration (text-to-mesh)
- [ ] Tripo AI proxy integration (text/image-to-mesh)
- [ ] AI texture generation (Stable Diffusion / DALL-E)
- [ ] AI audio/SFX generation
- [ ] Cloud state store (PostgreSQL + WebSocket sync)
- [ ] Team collaboration (merge conflict detection for scene files)

**Deliverable**: Pro subscription tier live.

### Phase 4: Advanced Domains (Weeks 11-14)
**Goal**: Pre-trained game-type agents + cloud builds.

- [ ] Game-type profiles (2D platformer, 3D FPS, top-down RPG, visual novel)
- [ ] Pre-trained agent fine-tuning (RAG on Godot docs + best practices)
- [ ] Cloud CI export (GitHub Actions integration)
- [ ] Advanced debugger integration (if godot-mcp spike is "go")
- [ ] C# support (post-release from godot-mcp)

### Phase 5: Scale & Ecosystem (Post-release)
**Goal**: Marketplace, community agents, enterprise.

- [ ] Agent marketplace (community-contributed agents for specific genres)
- [ ] Enterprise private cloud deployment
- [ ] Custom model training on studio codebases
- [ ] Godot 5 readiness

---

## 11. Risk Register

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| **Godot debugger API is incomplete** | Cannot deliver true breakpoint/step | Medium | Fallback to log-point debugging; spike first (Issue #110) |
| **Context window overflow in multi-agent** | Orchestrator state gets too large | Medium | State pruning; summarize completed tasks; limit DAG depth |
| **Agent conflict / race conditions** | Two agents overwrite same scene | Medium | Soft locks + Orchestrator arbitration; mandatory lock acquire |
| **AI model API costs escalate** | Pro tier margins compress | High | Rate limiting, caching, smaller models for simple tasks (Haiku/Mini) |
| **Godot API instability across versions** | Toolsets break | Low | Version gating in `godot-mcp`; compatibility matrix |
| **User resistance to Docker** | Local setup friction | Medium | Provide native Python install path as alternative (slower, but works) |
| **C# community pressure** | Delayed C# support frustrates users | Medium | Clear backlog issue (#106); community contributions welcome |
| **Nwiro Pro competition** | Nwiro expands to Godot | Low | Nwiro is UE5-only; our Godot-native depth is the moat |
| **Open-source core cannibalizes Pro** | Users self-host everything | Medium | Pro value is in AI APIs, team sync, cloud compute — not the engine bridge |

---

## 12. Success Metrics

| Metric | Target (Phase 2) | Target (Phase 4) |
|---|---|---|
| End-to-end scene creation time (prompt → working scene) | < 5 minutes | < 2 minutes |
| Agent tool call success rate | > 85% | > 95% |
| Token cost per task (Claude 3.5 Sonnet) | < $0.10 | < $0.05 |
| Human intervention required per task | 1-2 corrections | 0 (full autonomy) |
| Game-type scaffold coverage | 2 types | 6+ types |
| Community GitHub stars (agent repo) | 500 | 5,000 |
| Pro tier monthly recurring revenue | N/A | $10K+ |

---

## 13. Appendix: Nwiro Pro Tool Count Comparison

| Nwiro Category | Tool Count | Our Equivalent Tool Count (with gaps closed) |
|---|---|---|
| Blueprints | 18 | ~25 (GDScript + macros) |
| Materials | 12 | ~15 (shaders + visual shader) |
| World/Actors | 17 | ~20 (scene edit + 3D) |
| PIE Runtime | 14 | ~15 (runtime + input + testing) |
| Animation | 9 | ~10 |
| Sequencer | 6 | 0 (out of scope) |
| BP Debugger | 10 | 10 (if spike is "go") |
| Asset Dependency | 5 | ~8 |
| Enhanced Input | 5 | ~6 |
| Generic Asset | 3 | ~5 |
| Data Structures | 6 | ~4 |
| Behavior Trees | 7 | 0 (out of scope) |
| Widget/UMG | 17 | ~15 (theme + UI) |
| Niagara VFX | 4 | ~6 (particles) |
| State Trees | 3 | ~3 |
| IK Rigs | 5 | 0 (not planned) |
| Motion Matching | 4 | 0 (not planned) |
| Environment | 5 | ~6 |
| Physics | 4 | ~6 |
| Spline | 7 | ~7 |
| Navigation | 3 | ~4 |
| Audio | 3 | ~5 |
| Game Framework | 8 | ~6 |
| GAS | 6 | 0 (out of scope) |
| PCG | 4 | 0 (out of scope) |
| Level | 5 | ~5 |
| Landscape | 3 | 0 (out of scope) |
| Foliage | 4 | 0 (out of scope) |
| Networking | 3 | ~3 |
| World Partition | 2 | 0 (out of scope) |
| Macro Shortcuts | 4 | ~8 |
| Build/Validation | 5 | ~5 |
| Editor | 4 | ~5 |
| File Operations | 4 | ~4 |
| **Total Nwiro** | **~220** | **~190** (with planned gaps closed) |

**Key takeaway**: Even with all planned toolsets, we will not hit Nwiro's raw tool count because we explicitly exclude UE5-specific systems (GAS, PCG, Sequencer, World Partition) that have no Godot equivalent. Our moat is **depth in Godot-native workflows**, not breadth across engine-unique subsystems.

---

## 14. Document History

| Date | Author | Change |
|---|---|---|
| 2026-06-08 | OpenCode / hybridindie | Initial comprehensive research document compiled from Nwiro Pro analysis, godot-mcp architecture review, and multi-agent design sessions. |

---

*End of Document*
