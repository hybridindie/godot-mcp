"""External asset import tools (issue #108).

Generic drop-in for external files (local paths or HTTP URLs) and PBR material
assembly. This is the open-source foundation for external AI content pipelines
(e.g. Meshy, Tripo) without hard-coding provider-specific logic.

Gated ``asset_import`` toolset.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_server.bridge import Bridge
from mcp_server.categories import ASSET_IMPORT_TAG
from mcp_server.models.import_asset import (
    CreateMaterialResult,
    ImportAssetResult,
    ImportStatusResult,
)
from mcp_server.safety import MUTATING, READ_ONLY
from mcp_server.tools._route import route, run_or_preview

ASSET_IMPORT = {ASSET_IMPORT_TAG}

# Extension → Godot type mapping (auto-detect on import).
_EXT_TO_TYPE: dict[str, str] = {
    ".png": "Texture2D",
    ".jpg": "Texture2D",
    ".jpeg": "Texture2D",
    ".webp": "Texture2D",
    ".svg": "Texture2D",
    ".glb": "PackedScene",
    ".gltf": "PackedScene",
    ".obj": "Mesh",
    ".fbx": "PackedScene",
    ".wav": "AudioStreamWAV",
    ".ogg": "AudioStreamOggVorbis",
    ".mp3": "AudioStreamMP3",
    ".tres": "Resource",
    ".res": "Resource",
    ".tscn": "PackedScene",
    ".scn": "PackedScene",
    ".gd": "GDScript",
    ".cs": "CSharpScript",
    ".gdshader": "Shader",
}


def _detect_type(path: str) -> str | None:
    """Auto-detect Godot resource type from file extension."""
    ext = Path(path).suffix.lower()
    return _EXT_TO_TYPE.get(ext)


def _require_res_path(path: str, field: str = "target_path") -> None:
    if not path.startswith("res://"):
        raise ToolError(
            f"VALIDATION_ERROR: '{field}' must start with 'res://' (got '{path}')."
        )


def _is_url(source: str) -> bool:
    return source.startswith("http://") or source.startswith("https://")


async def _download_url(url: str) -> str:
    """Download ``url`` to a temporary file and return its absolute path.

    Streams the response to disk in 64 KiB chunks to avoid buffering the
    entire payload in memory. Raises ``ToolError`` on network or HTTP failure.
    """
    try:
        import httpx
    except ImportError as exc:
        raise ToolError(
            "INTERNAL_ERROR: httpx is not installed. "
            "Install it to enable URL download support."
        ) from exc

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "GET", url, follow_redirects=True
            ) as response:
                response.raise_for_status()
                suffix = Path(url.split("?")[0]).suffix or ".tmp"
                fd, tmp_path = tempfile.mkstemp(suffix=suffix)
                try:
                    with os.fdopen(fd, "wb") as tmp:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            tmp.write(chunk)
                    return tmp_path
                except Exception:
                    os.close(fd)
                    raise
    except httpx.HTTPStatusError as exc:
        raise ToolError(
            f"DOWNLOAD_FAILED: HTTP {exc.response.status_code} for '{url}'."
        ) from exc
    except httpx.RequestError as exc:
        raise ToolError(
            f"DOWNLOAD_FAILED: Network error downloading '{url}': {exc}."
        ) from exc


# ---------------------------------------------------------------------------
# Public tool registration
# ---------------------------------------------------------------------------


def register_import_asset(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the asset import tools."""

    @mcp.tool(meta=MUTATING, tags=ASSET_IMPORT)
    async def import_asset(
        source: str,
        target_path: str,
        options: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> ImportAssetResult:
        """Bring an external file into the Godot project.

        ``source`` may be a local filesystem path or an HTTP(S) URL.  The file is
        copied into ``target_path`` (``res://…``) and the editor filesystem is
        updated so Godot imports it on the next scan.

        ``options`` (optional dict):
        - ``overwrite`` (bool, default ``False``)
        - ``import_settings`` (dict, type-specific — e.g.
          ``{"type": "Texture2D", "compress": "lossy"}``)
        """
        _require_res_path(target_path)
        options = options or {}
        detected_type = _detect_type(target_path)

        preview = ImportAssetResult(
            imported=False,
            target_path=target_path,
            detected_type=detected_type,
            dry_run=True,
        )
        if dry_run:
            return preview

        local_source = source
        downloaded_tmp: str | None = None
        if _is_url(source):
            downloaded_tmp = await _download_url(source)
            local_source = downloaded_tmp

        params: dict[str, Any] = {
            "source": local_source,
            "target_path": target_path,
            "overwrite": options.get("overwrite", False),
            "import_settings": options.get("import_settings", {}),
        }
        try:
            result = await route(bridge, "cmd_import_asset", params)
        finally:
            if downloaded_tmp and os.path.exists(downloaded_tmp):
                os.unlink(downloaded_tmp)
        return ImportAssetResult(
            imported=result.get("imported", True),
            target_path=result.get("target_path", target_path),
            detected_type=result.get("detected_type") or detected_type,
            dry_run=False,
        )

    @mcp.tool(meta=MUTATING, tags=ASSET_IMPORT)
    async def create_material_from_textures(
        albedo: str = "",
        normal: str = "",
        roughness: str = "",
        metallic: str = "",
        ao: str = "",
        emission: str = "",
        path: str = "",
        dry_run: bool = False,
    ) -> CreateMaterialResult:
        """Assemble a PBR material from texture paths and save it as a ``.tres``.

        Creates a ``StandardMaterial3D`` and assigns whichever texture channels
        were provided.  ``path`` defaults to ``res://materials/generated_{rand}.tres``
        when omitted.
        """
        params: dict[str, Any] = {
            "albedo": albedo,
            "normal": normal,
            "roughness": roughness,
            "metallic": metallic,
            "ao": ao,
            "emission": emission,
            "path": path,
        }
        preview = {
            "material_path": path or "res://materials/generated_{rand}.tres",
            "created": False,
            "channels_set": [],
        }
        return await run_or_preview(
            dry_run,
            CreateMaterialResult,
            preview,
            bridge,
            "cmd_create_material_from_textures",
            params,
        )

    @mcp.tool(meta=READ_ONLY, tags=ASSET_IMPORT)
    async def get_import_status(target_path: str) -> ImportStatusResult:
        """Check whether ``target_path`` has been imported by the Godot editor.

        Looks in ``.godot/imported/`` for the corresponding import file and
        returns the detected type and last-modified time.
        """
        _require_res_path(target_path)
        result = await route(bridge, "cmd_get_import_status", {"target_path": target_path})
        return ImportStatusResult(
            imported=result.get("imported", False),
            last_modified=result.get("last_modified"),
            type=result.get("type"),
        )
