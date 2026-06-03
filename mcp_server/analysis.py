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
_CONNECTION = re.compile(
    r'\[connection signal="([^"]+)" from="([^"]+)" to="([^"]+)" method="([^"]+)"'
)
_NODE_HEADER = re.compile(r"^\[node ", re.MULTILINE)
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
                base = res.rsplit("/", 1)[0]
                index.entry_points.add(f"{base}/{script.group(1)}")


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
        for signal, src, dst, method in _CONNECTION.findall(text):
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
                    cycles.append([*cycle, dep])
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
            total_connections += len(_CONNECTION.findall(text))
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
