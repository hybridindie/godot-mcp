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
