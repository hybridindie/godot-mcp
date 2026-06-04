"""Canonical defaults for tool parameters ("default constants").

Every magic number or string that appears in a tool signature or a hard-coded
sleep / poll interval lives here so there is one place to change it. Constants
are grouped by domain and typed so ``mypy`` catches unit mismatches.

Import from here in ``mcp_server/tools/*.py`` instead of inlining values.
"""

from __future__ import annotations

# -- Timeouts (seconds) ---------------------------------------------------------
DEFAULT_RUN_TIMEOUT_SECONDS: float = 10.0
DEFAULT_EXPORT_TIMEOUT_SECONDS: float = 300.0

# -- Timeouts (milliseconds) ----------------------------------------------------
DEFAULT_INPUT_RECORDING_TIMEOUT_MS: int = 2000
DEFAULT_PERF_MONITORS_TIMEOUT_MS: int = 2000
DEFAULT_RUNTIME_INSPECT_TIMEOUT_MS: int = 2000
DEFAULT_ASSERT_NODE_TIMEOUT_MS: int = 1500

# -- Polling intervals ----------------------------------------------------------
DEFAULT_POLL_INTERVAL_SECONDS: float = 0.1
DEFAULT_PROBE_POLL_INTERVAL_SECONDS: float = 0.2

# -- Testing -------------------------------------------------------------------
DEFAULT_TEST_SETUP_MS: int = 800
DEFAULT_TEST_SETTLE_MS: int = 300
DEFAULT_STRESS_ITERATIONS: int = 100
DEFAULT_STRESS_DELAY_MS: int = 8
DEFAULT_STRESS_MAX_WAIT_SECONDS: float = 10.0
DEFAULT_STRESS_BUFFER_SECONDS: float = 0.5
DEFAULT_STRESS_MAX_ITERATIONS: int = 2000

# -- Search / Filesystem -------------------------------------------------------
DEFAULT_SEARCH_MAX_RESULTS: int = 200

# -- Particle systems -----------------------------------------------------------
DEFAULT_PARTICLE_AMOUNT: int = 8
DEFAULT_PARTICLE_LIFETIME: float = 1.0

# -- Runtime inspect -----------------------------------------------------------
DEFAULT_MONITOR_SAMPLES: int = 30

# -- 3D scene -------------------------------------------------------------------
DEFAULT_MESH_TYPE: str = "BoxMesh"
DEFAULT_MESH_INSTANCE_NAME: str = "MeshInstance3D"
DEFAULT_CAMERA_NAME: str = "Camera3D"
DEFAULT_LIGHT_TYPE: str = "DirectionalLight3D"
DEFAULT_WORLD_ENVIRONMENT_NAME: str = "WorldEnvironment"
DEFAULT_GRIDMAP_ORIENTATION: int = 0

# -- Physics -------------------------------------------------------------------
DEFAULT_COLLISION_NODE_TYPE: str = "CollisionShape2D"
DEFAULT_RAYCAST_NAME: str = "RayCast"
DEFAULT_RAYCAST_TYPE: str = "RayCast2D"

# -- Animation ------------------------------------------------------------------
DEFAULT_ANIMATION_LENGTH: float = 1.0
DEFAULT_ANIMATION_TRACK_TYPE: str = "value"
DEFAULT_ANIMATION_EASING: float = 1.0
DEFAULT_ANIMATION_TREE_NAME: str = "AnimationTree"
DEFAULT_ANIMATION_TREE_ROOT_TYPE: str = "AnimationNodeStateMachine"

# -- Audio ---------------------------------------------------------------------
DEFAULT_AUDIO_PLAYER_TYPE: str = "AudioStreamPlayer"
DEFAULT_AUDIO_BUS_VOLUME_DB: float = 0.0

# -- Navigation ----------------------------------------------------------------
DEFAULT_NAV_REGION_TYPE: str = "NavigationRegion2D"
DEFAULT_NAV_AGENT_TYPE: str = "NavigationAgent2D"

# -- Input simulation ----------------------------------------------------------
DEFAULT_INPUT_STRENGTH: float = 1.0
DEFAULT_INPUT_AXIS_VALUE: float = 1.0
DEFAULT_INPUT_DEADZONE: float = 0.5

# -- Theme / UI ---------------------------------------------------------------
DEFAULT_STYLEBOX_TYPE: str = "StyleBoxFlat"

# -- Shader -------------------------------------------------------------------
DEFAULT_SHADER_CODE: str = (
    "shader_type canvas_item;\n\nvoid fragment() {\n\tCOLOR = vec4(1.0);\n}\n"
)
