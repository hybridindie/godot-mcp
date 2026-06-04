"""Particle tools (issue #42).

Create and configure GPU particle systems over the bridge: the node + its
ParticleProcessMaterial, a color-over-lifetime gradient, and named VFX presets.
Gated `particles` toolset; all `mutating` (UndoRedo-wrapped addon-side) with
`dry_run`. Generic Godot — pass the node type names (``GPUParticles2D`` /
``GPUParticles3D``).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import PARTICLES_TAG
from mcp_server.defaults import (
    DEFAULT_PARTICLE_AMOUNT,
    DEFAULT_PARTICLE_LIFETIME,
)
from mcp_server.models.particles import (
    CreateParticlesResult,
    ParticleGradientResult,
    ParticleMaterialResult,
    ParticlePresetResult,
)
from mcp_server.safety import MUTATING, enforce_preconditions, require_node_exists
from mcp_server.tools._route import route

PARTICLES = {PARTICLES_TAG}

# Generic VFX presets recognized by the addon (no game vocabulary).
PARTICLE_PRESETS = ("fire", "smoke", "explosion", "sparks")


def register_particles(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the particle tools."""

    @mcp.tool(meta=MUTATING, tags=PARTICLES)
    @enforce_preconditions
    async def create_particles(
        parent_path: str,
        particles_type: str = "GPUParticles2D",
        name: str = "",
        amount: int = DEFAULT_PARTICLE_AMOUNT,
        lifetime: float = DEFAULT_PARTICLE_LIFETIME,
        properties: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> CreateParticlesResult:
        """Add a GPU particle node (GPUParticles2D / GPUParticles3D) under
        ``parent_path`` with a fresh ParticleProcessMaterial. ``amount``/``lifetime``
        and any node ``properties`` (e.g. ``one_shot``, ``explosiveness``) are applied.
        """
        await require_node_exists(bridge, parent_path)
        if dry_run:
            return CreateParticlesResult(
                node_path="", particles_type=particles_type, created=False, dry_run=True
            )
        params = {
            "parent_path": parent_path,
            "particles_type": particles_type,
            "name": name or particles_type,
            "amount": amount,
            "lifetime": lifetime,
            "properties": properties or {},
        }
        return CreateParticlesResult(**await route(bridge, "cmd_create_particles", params))

    @mcp.tool(meta=MUTATING, tags=PARTICLES)
    @enforce_preconditions
    async def set_particle_material(
        node_path: str, properties: dict[str, Any], dry_run: bool = False
    ) -> ParticleMaterialResult:
        """Configure the ParticleProcessMaterial of the particle node at ``node_path``
        (creating one if absent): set ``properties`` such as ``gravity``,
        ``initial_velocity_min``/``max``, ``scale_min``/``max``, ``spread``, ``color``.
        """
        await require_node_exists(bridge, node_path)
        if dry_run:
            return ParticleMaterialResult(node_path=node_path, properties={}, dry_run=True)
        params = {"node_path": node_path, "properties": properties}
        return ParticleMaterialResult(**await route(bridge, "cmd_set_particle_material", params))

    @mcp.tool(meta=MUTATING, tags=PARTICLES)
    @enforce_preconditions
    async def set_particle_color_gradient(
        node_path: str,
        colors: list[Any],
        offsets: list[float] | None = None,
        dry_run: bool = False,
    ) -> ParticleGradientResult:
        """Set the color-over-lifetime ramp on the particle node's process material:
        ``colors`` is a list of color stops (HTML strings like "#ff8800" or
        ``[r,g,b,a]``); ``offsets`` are 0..1 positions (defaults to evenly spaced).
        Builds a GradientTexture1D and assigns it to ``color_ramp``.
        """
        await require_node_exists(bridge, node_path)
        if dry_run:
            return ParticleGradientResult(node_path=node_path, stops=len(colors), dry_run=True)
        params: dict[str, Any] = {"node_path": node_path, "colors": colors}
        if offsets is not None:
            params["offsets"] = offsets
        return ParticleGradientResult(
            **await route(bridge, "cmd_set_particle_color_gradient", params)
        )

    @mcp.tool(meta=MUTATING, tags=PARTICLES)
    @enforce_preconditions
    async def apply_particle_preset(
        node_path: str, preset: str, dry_run: bool = False
    ) -> ParticlePresetResult:
        """Apply a generic VFX preset to the particle node at ``node_path`` — one of
        fire / smoke / explosion / sparks. Configures the node + process material +
        color ramp in one call as a starting point you can then tweak.
        """
        await require_node_exists(bridge, node_path)
        if dry_run:
            return ParticlePresetResult(node_path=node_path, preset=preset, dry_run=True)
        params = {"node_path": node_path, "preset": preset}
        return ParticlePresetResult(**await route(bridge, "cmd_apply_particle_preset", params))
