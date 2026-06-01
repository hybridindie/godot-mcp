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
