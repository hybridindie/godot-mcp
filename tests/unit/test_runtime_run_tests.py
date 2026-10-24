"""Unit: the GUT runner picks -gtest for one file and -gdir otherwise (#775)."""

from __future__ import annotations

from mcp_server.config import ServerConfig
from mcp_server.runtime import GodotRunner, RunOutput


async def test_run_tests_targets_a_file_or_directory() -> None:
    runner = GodotRunner(ServerConfig(), binary="/bin/true")
    calls: list[list[str]] = []

    async def fake_exec(
        command: list[str | None], timeout: float, cwd: str | None = None
    ) -> RunOutput:
        calls.append([c for c in command if c is not None])
        return RunOutput(command=[])

    runner._exec = fake_exec  # type: ignore[method-assign]

    await runner.run_tests("/proj", "res://test", 10)
    await runner.run_tests("/proj", "res://test", 10, test_file="res://test/one.gd")
    assert "-gdir=res://test" in calls[0] and not any(c.startswith("-gtest") for c in calls[0])
    assert "-gtest=res://test/one.gd" in calls[1]
    assert not any(c.startswith("-gdir") for c in calls[1])
