"""Tool-independent parsing of GUT command-line output (issue #206).

Kept free of FastMCP / tool-layer imports (cf. ``scripts_parse.py``) so the
testing tool can use it without pulling in tool-registration code.

GUT's stdout summary varies a little across versions, so counts use lenient
regexes and the overall pass/fail is derived from them. Per-failure detail
(test name, file, line) is **best-effort** scraped from the run log.
"""

from __future__ import annotations

import re

from mcp_server.models.testing import RunTestsResult, TestFailure

_PASSING_RE = re.compile(r"Passing(?:\s+tests)?\s+(\d+)", re.IGNORECASE)
_FAILING_RE = re.compile(r"Failing(?:\s+tests)?\s+(\d+)", re.IGNORECASE)
# Fallback summary line, e.g. "1 of 3 tests failed (3 ran)".
_OF_Y_RE = re.compile(r"(\d+)\s+of\s+(\d+)\s+tests?\s+failed", re.IGNORECASE)

_FILE_RE = re.compile(r"(res://\S+?\.gd)")
_TEST_RE = re.compile(r"^\s+([A-Za-z_]\w*)\s*$")
_FAILED_RE = re.compile(r"\[Failed\]:?\s*(.*)")
_AT_LINE_RE = re.compile(r"at line (\d+)", re.IGNORECASE)


def _counts(text: str) -> tuple[int, int, int] | None:
    """Return (passed, failed, total) from the totals block, or None if absent."""
    passing = _PASSING_RE.search(text)
    failing = _FAILING_RE.search(text)
    if passing and failing:
        p, f = int(passing.group(1)), int(failing.group(1))
        return p, f, p + f
    # GUT 9.7+ omits the "Failing Tests" line when there are zero failures.
    # If we have a passing count but no failing line, assume 0 failures.
    if passing:
        p = int(passing.group(1))
        return p, 0, p
    of_y = _OF_Y_RE.search(text)
    if of_y:
        failed, total = int(of_y.group(1)), int(of_y.group(2))
        return total - failed, failed, total
    return None


def _failures(lines: list[str]) -> list[TestFailure]:
    """Best-effort: pair each ``[Failed]`` marker with the nearest test/file/line."""
    failures: list[TestFailure] = []
    current_file: str | None = None
    current_test = ""
    for i, line in enumerate(lines):
        file_match = _FILE_RE.search(line)
        if file_match and not _FAILED_RE.search(line):
            current_file = file_match.group(1)
        test_match = _TEST_RE.match(line)
        if test_match and not _FILE_RE.search(line):
            current_test = test_match.group(1)
        failed_match = _FAILED_RE.search(line)
        if failed_match:
            line_no: int | None = None
            for look in lines[i : i + 3]:
                at = _AT_LINE_RE.search(look)
                if at:
                    line_no = int(at.group(1))
                    break
            failures.append(
                TestFailure(
                    test=current_test,
                    file=current_file,
                    line=line_no,
                    message=failed_match.group(1).strip(),
                )
            )
    return failures


def parse_gut_results(stdout: str) -> RunTestsResult:
    """Parse GUT stdout into a ``RunTestsResult`` (framework="gut", ran=True).

    The tool layer fills ``timed_out`` / ``exit_code`` / ``framework_absent``.
    """
    counts = _counts(stdout)
    passed, failed, total = counts if counts else (0, 0, 0)
    return RunTestsResult(
        ran=True,
        framework="gut",
        passed=passed,
        failed=failed,
        total=total,
        failures=_failures(stdout.splitlines()),
        raw_summary=stdout.strip()[-2000:],
    )
