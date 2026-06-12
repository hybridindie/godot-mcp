"""Tool category tags (issue #26).

Bare string constants in a dependency-free leaf module so both the safety/toolset
machinery and the tool modules can tag tools without import cycles. Every tool is
tagged with exactly one of these; `core` is always exposed, the rest are gated
(see toolsets.py).
"""

from __future__ import annotations

CORE_TAG = "core"
INSPECTION_TAG = "inspection"
SCENE_EDIT_TAG = "scene_edit"
RUNTIME_TAG = "runtime"
SCRIPTS_TAG = "scripts"
RESOURCES_EDIT_TAG = "resources_edit"
PROJECT_TAG = "project"
EDITOR_TAG = "editor"
PHYSICS_TAG = "physics"
ANIMATION_TAG = "animation"
SCENE_3D_TAG = "scene_3d"
PARTICLES_TAG = "particles"
NAVIGATION_TAG = "navigation"
AUDIO_TAG = "audio"
TILEMAP_TAG = "tilemap"
THEME_UI_TAG = "theme_ui"
SHADER_TAG = "shader"
INPUT_TAG = "input"
INPUT_MAP_TAG = "input_map"
TESTING_TAG = "testing"
PROFILING_TAG = "profiling"
BATCH_TAG = "batch"
ANALYSIS_TAG = "analysis"
EXPORT_TAG = "export"
DEBUGGER_TAG = "debugger"
ASSET_IMPORT_TAG = "asset_import"
VISUAL_SHADER_TAG = "visual_shader"
PROJECT_SCAFFOLD_TAG = "project_scaffold"
COMPOSITE_TAG = "composite"
