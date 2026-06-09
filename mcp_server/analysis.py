"""Static project analysis (issue #49).

Pure, bridge-free analysis over a Godot project's files: unused resources, signal flow,
circular script dependencies, and scene-complexity stats. Kept out of the tool handlers
(Article I) — the tools just resolve the project dir and call these.

These are text/heuristic analyses of ``.tscn`` / ``.tres`` / ``.gd`` / ``project.godot``,
so dynamically-built paths (string-concatenated ``load()``, etc.) aren't tracked — callers
should treat results as a strong hint, not ground truth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Resource files we consider as "candidates" for unused detection.
RESOURCE_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".webp",
    ".bmp",
    ".tres",
    ".res",
    ".ogg",
    ".wav",
    ".mp3",
    ".gd",
    ".tscn",
    ".scn",
    ".gdshader",
    ".ttf",
    ".otf",
    ".material",
    ".obj",
    ".glb",
    ".gltf",
    ".json",
    ".csv",
}
# Text files we scan for ``res://`` references and structure.
_REF_EXTS = {".tscn", ".tres", ".gd", ".gdshader", ".godot", ".cfg"}
_SKIP_DIRS = {".godot", ".git", ".import"}

_RES_REF = re.compile(r"res://[^\s\"'()\[\]]+")
_UID_REF = re.compile(r"uid://[^\s\"'()\[\]]+")
_EXT_RESOURCE = re.compile(r'\[ext_resource\s+[^\]]*type="([^"]+)"[^\]]*path="([^"]+)"')
_EXT_RESOURCE_ID = re.compile(r'\[ext_resource\s+[^\]]*id="([^"]+)"[^\]]*path="([^"]+)"')
_SUB_RESOURCE = re.compile(r'\[sub_resource\s+[^\]]*type="([^"]+)"')
_NODE_HEADER = re.compile(r"^\[node ", re.MULTILINE)
_NODE_HEADER_LINE = re.compile(r'^\[node\s+name="([^"]+)"\s+type="([^"]+)"')
_SCRIPT_ASSIGN = re.compile(r'script\s*=\s*ExtResource\("([^"]+)"\)')
_CONNECTION = re.compile(
    r'\[connection signal="([^"]+)" from="([^"]+)" to="([^"]+)" method="([^"]+)"'
)
_SIGNAL_CONN = _CONNECTION
_NODE_PARENT = re.compile(r'parent="([^"]+)"')
_SCRIPT_DEP = re.compile(
    r'(?:preload|load)\(\s*"(res://[^"]+\.gd)"\s*\)|extends\s+"(res://[^"]+\.gd)"'
)


@dataclass
class ProjectIndex:
    project_dir: Path
    resources: dict[str, Path] = field(default_factory=dict)  # res:// path -> file
    texts: dict[str, str] = field(default_factory=dict)  # res:// path -> file text
    referenced: set[str] = field(default_factory=set)  # res:// paths referenced anywhere
    entry_points: set[str] = field(default_factory=set)  # main scene + autoloads + plugins


def _to_res(project_dir: Path, path: Path) -> str:
    return "res://" + path.relative_to(project_dir).as_posix()


def scan(project_dir: Path) -> ProjectIndex:
    """Walk the project once: index resource files, read text files, and collect every
    ``res://`` reference plus entry points (main scene, autoloads, plugin scripts).
    """
    index = ProjectIndex(project_dir=project_dir)
    for path in sorted(project_dir.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.relative_to(project_dir).parts):
            continue
        res = _to_res(project_dir, path)
        ext = path.suffix.lower()
        if ext in RESOURCE_EXTS:
            index.resources[res] = path
        if ext in _REF_EXTS:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            index.texts[res] = text
            for ref in _RES_REF.findall(text):
                index.referenced.add(ref.rstrip(".,"))
    _collect_entry_points(index)
    return index


def _collect_entry_points(index: ProjectIndex) -> None:
    godot = index.texts.get("res://project.godot", "")
    main = re.search(r'run/main_scene\s*=\s*"(res://[^"]+)"', godot)
    if main:
        index.entry_points.add(main.group(1))
    for auto in re.findall(r'^\s*[\w.]+\s*=\s*"\*?(res://[^"]+)"', godot, re.MULTILINE):
        index.entry_points.add(auto)
    # Enabled plugins: their plugin.cfg `script=` is the EditorPlugin entry point.
    for res, text in index.texts.items():
        if res.endswith("plugin.cfg"):
            script = re.search(r'script\s*=\s*"([^"]+)"', text)
            if script:
                value = script.group(1)
                # `script=` may be absolute (res://...) or relative to the addon dir.
                if value.startswith("res://"):
                    index.entry_points.add(value)
                else:
                    index.entry_points.add(f"{res.rsplit('/', 1)[0]}/{value}")


def find_unused_resources(index: ProjectIndex) -> dict[str, Any]:
    """Resource files not referenced by any project file and not an entry point. Heuristic
    — dynamically-loaded or externally-referenced resources can be false positives.
    """
    unused = sorted(
        res
        for res in index.resources
        if res not in index.referenced
        and res not in index.entry_points
        and res != "res://project.godot"
    )
    return {"unused": unused, "scanned": len(index.resources), "referenced": len(index.referenced)}


def analyze_signal_flow(index: ProjectIndex, scene: str = "") -> dict[str, Any]:
    """Signal connections declared in scene files (``[connection ...]``). Limited to
    ``scene`` when given, else all scenes.
    """
    connections: list[dict[str, str]] = []
    for res, text in index.texts.items():
        if not res.endswith((".tscn", ".scn")):
            continue
        if scene and res != scene:
            continue
        for signal, src, dst, method in _SIGNAL_CONN.findall(text):
            connections.append(
                {"scene": res, "signal": signal, "from": src, "to": dst, "method": method}
            )
    return {"connections": connections, "count": len(connections)}


def detect_circular_dependencies(index: ProjectIndex) -> dict[str, Any]:
    """Cycles in the script preload/extends graph among project ``.gd`` files."""
    graph: dict[str, set[str]] = {}
    for res, text in index.texts.items():
        if not res.endswith(".gd"):
            continue
        deps: set[str] = set()
        for a, b in _SCRIPT_DEP.findall(text):
            dep = a or b
            if dep and dep != res and dep in index.resources:
                deps.add(dep)
        graph[res] = deps
    cycles = _find_cycles(graph)
    return {"cycles": cycles, "count": len(cycles)}


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Return distinct dependency cycles (each as an ordered path) via DFS."""
    cycles: list[list[str]] = []
    seen_keys: set[frozenset[str]] = set()
    visiting: list[str] = []
    on_stack: set[str] = set()
    done: set[str] = set()

    def dfs(node: str) -> None:
        visiting.append(node)
        on_stack.add(node)
        for dep in sorted(graph.get(node, ())):
            if dep in on_stack:
                cycle = visiting[visiting.index(dep) :]
                key = frozenset(cycle)
                if key not in seen_keys:
                    seen_keys.add(key)
                    cycles.append(list(cycle))  # ordered, unique paths (no closing dupe)
            elif dep not in done:
                dfs(dep)
        on_stack.discard(node)
        visiting.pop()
        done.add(node)

    for node in sorted(graph):
        if node not in done:
            dfs(node)
    return cycles


def project_stats(index: ProjectIndex) -> dict[str, Any]:
    """Scene/script/resource counts, total nodes, connection count, and the busiest scenes."""
    by_extension: dict[str, int] = {}
    for path in index.resources.values():
        ext = path.suffix.lower()
        by_extension[ext] = by_extension.get(ext, 0) + 1
    scenes_by_nodes: list[dict[str, Any]] = []
    total_nodes = 0
    total_connections = 0
    for res, text in index.texts.items():
        if res.endswith((".tscn", ".scn")):
            nodes = len(_NODE_HEADER.findall(text))
            total_nodes += nodes
            total_connections += len(_SIGNAL_CONN.findall(text))
            scenes_by_nodes.append({"scene": res, "nodes": nodes})
    scenes_by_nodes.sort(key=lambda s: s["nodes"], reverse=True)
    return {
        "scenes": sum(1 for r in index.texts if r.endswith((".tscn", ".scn"))),
        "scripts": by_extension.get(".gd", 0),
        "resources": len(index.resources),
        "total_nodes": total_nodes,
        "connections": total_connections,
        "by_extension": by_extension,
        "busiest_scenes": scenes_by_nodes[:10],
    }


# ---------------------------------------------------------------------------
# Issue #111 — asset dependency, orphan detection, scene integrity
# ---------------------------------------------------------------------------


def _ext_resource_map(text: str) -> dict[str, str]:
    """Map ExtResource id -> path for a scene/resource file."""
    mapping: dict[str, str] = {}
    for block in re.findall(r'\[ext_resource\s+[^\]]*\]', text):
        id_match = re.search(r'id="([^"]+)"', block)
        path_match = re.search(r'path="([^"]+)"', block)
        if id_match and path_match:
            mapping[id_match.group(1)] = path_match.group(1)
    return mapping


def _ext_resource_type_map(text: str) -> dict[str, tuple[str, str]]:
    """Map ExtResource id -> (type, path) for a scene/resource file."""
    mapping: dict[str, tuple[str, str]] = {}
    for block in re.findall(r'\[ext_resource\s+[^\]]*\]', text):
        id_match = re.search(r'id="([^"]+)"', block)
        type_match = re.search(r'type="([^"]+)"', block)
        path_match = re.search(r'path="([^"]+)"', block)
        if id_match and type_match and path_match:
            mapping[id_match.group(1)] = (type_match.group(1), path_match.group(1))
    return mapping


def _collect_references(text: str, res: str) -> set[str]:
    """All res:// / uid:// refs found in a file's text, plus ext_resources."""
    refs: set[str] = set()
    refs.update(_RES_REF.findall(text))
    refs.update(_UID_REF.findall(text))
    # For scenes/resources, also explicitly parse ext_resource paths
    if res.endswith((".tscn", ".tres", ".scn")):
        for block in re.findall(r'\[ext_resource\s+[^\]]*\]', text):
            path_match = re.search(r'path="([^"]+)"', block)
            if path_match:
                refs.add(path_match.group(1))
    return refs


def analyze_dependencies(index: ProjectIndex, resource_path: str) -> dict[str, Any]:
    """Parse a resource file and extract all ``res://`` / ``uid://`` references.
    Recurse into sub-dependencies up to a depth limit.
    """
    if resource_path not in index.texts and resource_path not in index.resources:
        return {"path": resource_path, "type": "", "references": [], "referencers": []}

    visited: set[str] = set()
    references: list[str] = []

    def _dfs(path: str, depth: int) -> None:
        if depth > 5 or path in visited:
            return
        visited.add(path)
        text = index.texts.get(path, "")
        if not text:
            return
        for ref in sorted(_collect_references(text, path)):
            if ref.startswith(("res://", "uid://")) and ref not in visited:
                references.append(ref)
                if ref in index.texts:
                    _dfs(ref, depth + 1)

    _dfs(resource_path, 0)
    # deduplicate while preserving order
    seen: set[str] = set()
    unique_refs: list[str] = []
    for r in references:
        if r not in seen:
            seen.add(r)
            unique_refs.append(r)

    # Type inference
    rtype = ""
    ext = Path(resource_path).suffix.lower()
    if ext == ".gd":
        rtype = "GDScript"
    elif ext in {".tscn", ".scn"}:
        rtype = "PackedScene"
    elif ext == ".tres":
        rtype = "Resource"
    elif ext in {".png", ".jpg", ".jpeg", ".svg", ".webp", ".bmp"}:
        rtype = "Texture2D"
    elif ext in {".ogg", ".wav", ".mp3"}:
        rtype = "AudioStream"
    text = index.texts.get(resource_path, "")
    type_map = _ext_resource_type_map(text)
    if type_map:
        # any parsed ext_resource type overrides generic suffix inference
        first = next(iter(type_map.values()))
        rtype = first[0]

    # referencers = files that reference this path
    referencers: list[str] = sorted(
        res for res, text in index.texts.items() if resource_path in _collect_references(text, res)
    )

    return {
        "path": resource_path,
        "type": rtype,
        "references": unique_refs,
        "referencers": referencers,
    }


def find_orphaned_resources(
    index: ProjectIndex, scan_dir: str = "res://", resource_types: list[str] | None = None
) -> dict[str, Any]:
    """Resource files not referenced by any project file (excluding entry points).
    ``scan_dir`` narrows the scope (default whole project). ``resource_types`` filters
    by Godot type string (e.g. ``["Texture2D"]``); when omitted, all resource types
    are considered. Excludes ``.godot/`` and ``addons/`` by default.
    """
    orphaned: list[dict[str, Any]] = []
    for res, path in index.resources.items():
        if not res.startswith(scan_dir):
            continue
        # skip .godot cache and addons by default
        if "/.godot/" in res or "/addons/" in res:
            continue
        if res in index.referenced or res in index.entry_points:
            continue
        ext = path.suffix.lower()
        rtype = ""
        if ext in {".png", ".jpg", ".jpeg", ".svg", ".webp", ".bmp"}:
            rtype = "Texture2D"
        elif ext in {".ogg", ".wav", ".mp3"}:
            rtype = "AudioStream"
        elif ext == ".tres":
            rtype = "Resource"
        elif ext in {".tscn", ".scn"}:
            rtype = "PackedScene"
        elif ext == ".gd":
            rtype = "GDScript"
        if resource_types and rtype not in resource_types:
            continue
        estimated_size = path.stat().st_size if path.exists() else 0
        orphaned.append({"path": res, "type": rtype, "estimated_size": estimated_size})
    orphaned.sort(key=lambda o: o["path"])
    return {"orphaned": orphaned, "scanned": len(index.resources)}


def validate_scene_integrity(index: ProjectIndex, scene_path: str) -> dict[str, Any]:
    """Validate a scene file for broken references and malformed signal connections.
    Returns ``valid`` only when zero errors are found; warnings are non-blocking.
    """
    text = index.texts.get(scene_path, "")
    if not text:
        return {
            "valid": False,
            "errors": [{"severity": "error", "message": f"Scene not found: {scene_path}"}],
            "warnings": [],
        }

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    ext_map = _ext_resource_map(text)
    ext_type_map = _ext_resource_type_map(text)

    # broken ext_resource paths
    for _rid, (rtype, path) in ext_type_map.items():
        if path.startswith("res://") and path not in index.resources:
            errors.append(
                {
                    "severity": "error",
                    "message": f"Missing ext_resource: {path} ({rtype})",
                    "node_path": "",
                    "property": "",
                }
            )

    # collect node names for signal target validation
    node_names: set[str] = set()
    for line in text.splitlines():
        m = _NODE_HEADER_LINE.match(line)
        if m:
            node_names.add(m.group(1))

    # broken script assignments (resolve ExtResource id -> path)
    for line in text.splitlines():
        m = _SCRIPT_ASSIGN.search(line)
        if m:
            rid = m.group(1)
            script_path = ext_map.get(rid)
            if (
                script_path
                and script_path.startswith("res://")
                and script_path not in index.resources
            ):
                errors.append(
                    {
                        "severity": "error",
                        "message": f"Missing script: {script_path}",
                        "node_path": "",
                        "property": "script",
                    }
                )

    # broken signal connections
    for signal, src, dst, method in _SIGNAL_CONN.findall(text):
        for target in (src, dst):
            if target != "." and target not in node_names:
                errors.append(
                    {
                        "severity": "error",
                        "message": (
                            f"Signal '{signal}' connection points to missing node "
                            f"'{target}' (method '{method}')"
                        ),
                        "node_path": target,
                        "property": "",
                    }
                )

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def cross_scene_find_refs(index: ProjectIndex, target_path: str) -> dict[str, Any]:
    """Scan all project files for references to ``target_path`` (or its ``uid://``).
    Returns which scenes, resources, and scripts mention it.
    """
    scenes: list[str] = []
    resources: list[str] = []
    scripts: list[str] = []

    for res, text in index.texts.items():
        if target_path in text:
            if res.endswith((".tscn", ".scn")):
                scenes.append(res)
            elif res.endswith(".tres"):
                resources.append(res)
            elif res.endswith(".gd"):
                scripts.append(res)

    return {
        "scenes": sorted(set(scenes)),
        "resources": sorted(set(resources)),
        "scripts": sorted(set(scripts)),
    }
