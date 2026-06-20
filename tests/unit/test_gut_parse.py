"""Unit tests for GUT output parsing (issue #206).

The parser turns GUT's command-line stdout into a structured ``RunTestsResult``:
reliable counts + overall pass/fail, plus best-effort per-failure detail. Tested
against captured representative GUT output so no live editor is needed.
"""

from __future__ import annotations

from mcp_server.gut_parse import parse_gut_results

_GUT_PASS = """\
GUT version:  9.3.0
Running tests
res://test/test_player.gd
  test_health_starts_full
  test_takes_damage

=============================================
= Totals
=============================================
Scripts            1
Passing tests      2
Failing tests      0
Risky/Pending      0
Asserts            4
Time               0.101s

---- All tests passed! ----
Tests finished.
"""

_GUT_FAIL = """\
GUT version:  9.3.0
Running tests
res://test/test_player.gd
  test_health_starts_full
res://test/test_enemy.gd
  test_spawns
    [Failed]:  Expected [3] to equal [2]
        at line 14

=============================================
= Totals
=============================================
Scripts            2
Passing tests      2
Failing tests      1
Risky/Pending      0
Asserts            5
Time               0.214s

---- 1 of 3 tests failed (3 ran). ----
Tests finished.
"""


def test_parses_all_passing() -> None:
    r = parse_gut_results(_GUT_PASS)
    assert r.ran is True
    assert r.framework == "gut"
    assert r.passed == 2
    assert r.failed == 0
    assert r.total == 2
    assert r.failures == []


def test_parses_failures_with_counts() -> None:
    r = parse_gut_results(_GUT_FAIL)
    assert r.passed == 2
    assert r.failed == 1
    assert r.total == 3
    assert len(r.failures) == 1
    f = r.failures[0]
    assert "Expected [3] to equal [2]" in f.message
    # best-effort detail: the failing test + its script + line
    assert f.test == "test_spawns"
    assert f.file == "res://test/test_enemy.gd"
    assert f.line == 14


def test_unparseable_output_is_safe() -> None:
    r = parse_gut_results("garbage with no totals")
    assert r.ran is True
    assert r.passed == 0 and r.failed == 0 and r.total == 0
    assert r.failures == []
