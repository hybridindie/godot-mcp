"""Unit: mutating results declare how they can be reversed (#760)."""

from __future__ import annotations

from mcp_server.models.batch import BatchSetResult, CrossSceneResult
from mcp_server.models.composite import ApplyNodeEditsResult, BatchCreateNodesResult
from mcp_server.models.import_asset import ImportAssetResult
from mcp_server.models.mutation import ConnectSignalResult, CreateNodeResult
from mcp_server.models.project_fs import (
    DeleteResourceFileResult,
    MoveResourceFileResult,
    SetSettingResult,
)
from mcp_server.models.project_scaffold import ScaffoldProjectResult


def test_undo_family_reports_undo() -> None:
    assert CreateNodeResult(node_path="A", created=True).reversible_by == "undo"
    assert DeleteResourceFileResult(path="res://a.tscn", deleted=True).reversible_by == "undo"
    assert (
        ConnectSignalResult(
            source_path="A",
            signal_name="x",
            target_path="B",
            method_name="f",
            connected=True,
        ).reversible_by
        == "undo"
    )


def test_non_undoable_changes_report_none() -> None:
    assert BatchSetResult(property="visible", undoable=False).reversible_by == "none"
    assert BatchCreateNodesResult(undoable=False).reversible_by == "none"
    assert ApplyNodeEditsResult(undoable=False).reversible_by == "none"
    assert MoveResourceFileResult(old_path="res://a", new_path="res://b").reversible_by == "none"
    assert SetSettingResult(name="application/run/main_scene").reversible_by == "none"
    assert ScaffoldProjectResult(created=True).reversible_by == "none"
    assert ImportAssetResult(target_path="res://a.png", imported=True).reversible_by == "none"
    assert CrossSceneResult().reversible_by == "none"


def test_undoable_batch_stays_undo() -> None:
    assert BatchSetResult(property="visible", undoable=True).reversible_by == "undo"
    assert BatchCreateNodesResult(undoable=True).reversible_by == "undo"


def test_remaining_families_report_their_strategy() -> None:
    from mcp_server.models.audio import AudioBusResult
    from mcp_server.models.composite import ComposeNodeResult
    from mcp_server.models.input_map import AddInputActionResult
    from mcp_server.models.mutation import CreateSceneResult, SaveSceneResult
    from mcp_server.models.run_commands import RunCommandsResult
    from mcp_server.models.scripts import WriteScriptResult
    from mcp_server.models.undo import UndoResult

    assert AudioBusResult(index=0, name="Master").reversible_by == "undo"
    assert ComposeNodeResult(node_path="A", created=True).reversible_by == "undo"
    assert AddInputActionResult(name="jump", added=True).reversible_by == "none"
    assert SaveSceneResult(saved=True).reversible_by == "none"
    create_scene = CreateSceneResult(
        scene_path="res://a.tscn", root_type="Node2D", created=True
    )
    assert create_scene.reversible_by == "none"
    assert RunCommandsResult(ok_all=True, count=1).reversible_by == "none"
    write = WriteScriptResult(script_path="res://a.gd", created=True)
    assert write.reversible_by == "undo"
    assert write.model_dump()["reversible_by"] == "undo"
    undo = UndoResult(dry_run=False, requested=1, undone=1)
    assert undo.reversible_by == "undo"
    assert undo.model_dump()["reversible_by"] == "undo"


def test_every_mutation_tool_result_declares_reversibility() -> None:
    import ast
    import importlib
    import pkgutil
    from pathlib import Path

    import mcp_server.models

    classes: dict[str, object] = {}
    for mod_info in pkgutil.iter_modules(mcp_server.models.__path__):
        mod = importlib.import_module(f"mcp_server.models.{mod_info.name}")
        for name, value in vars(mod).items():
            if isinstance(value, type) and hasattr(value, "model_fields"):
                classes.setdefault(name, value)

    missing: list[str] = []
    for path in sorted(Path("mcp_server/tools").glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            mutating = False
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                    continue
                if dec.func.attr != "tool":
                    continue
                for kw in dec.keywords:
                    if kw.arg == "meta" and isinstance(kw.value, ast.Name):
                        if kw.value.id in ("MUTATING", "DESTRUCTIVE"):
                            mutating = True
            if not mutating:
                continue
            ret = ast.unparse(node.returns).split("[")[0] if node.returns else ""
            cls = classes.get(ret)
            if cls is None or "reversible_by" not in getattr(cls, "model_fields", {}):
                missing.append(f"{path.name}:{node.name} -> {ret}")
    assert not missing, "mutation results missing reversible_by:\n" + "\n".join(missing)
