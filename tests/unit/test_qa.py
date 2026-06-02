"""Unit tests for the QA logic (issue #37): image diff, assertions, fuzz generation."""

from __future__ import annotations

import pytest

from mcp_server.qa import (
    ImageCompareError,
    compare_images,
    encode_png,
    evaluate_assertion,
    random_input_events,
)


def _solid(width: int, height: int, rgba: tuple[int, int, int, int]) -> str:
    row = list(rgba) * width
    return encode_png(width, height, [row[:] for _ in range(height)])


def test_identical_images_match() -> None:
    img = _solid(4, 4, (10, 20, 30, 255))
    result = compare_images(img, img)
    assert result["match"] is True
    assert result["same_size"] is True
    assert result["diff_pixels"] == 0
    assert result["diff_ratio"] == 0.0


def test_different_images_report_diff() -> None:
    a = _solid(2, 2, (0, 0, 0, 255))
    b = _solid(2, 2, (255, 255, 255, 255))
    result = compare_images(a, b)
    assert result["match"] is False
    assert result["diff_pixels"] == 4
    assert result["diff_ratio"] == 1.0
    assert result["mean_abs_diff"] > 0.5


def test_tolerance_absorbs_small_diff() -> None:
    a = _solid(2, 2, (100, 100, 100, 255))
    b = _solid(2, 2, (105, 100, 100, 255))  # 5/255 ≈ 0.0196 off on one channel
    assert compare_images(a, b, tolerance=0.0)["match"] is False
    assert compare_images(a, b, tolerance=0.05)["match"] is True


def test_tolerance_is_clamped_to_one() -> None:
    # tolerance > 1 must not keep growing the threshold; it's capped at the 1.0 behavior.
    a = _solid(2, 2, (0, 0, 0, 255))
    b = _solid(2, 2, (255, 255, 255, 255))
    assert compare_images(a, b, tolerance=5.0) == compare_images(a, b, tolerance=1.0)
    # a large-but-sub-max tolerance still flags a full black/white difference
    assert compare_images(a, b, tolerance=0.9)["match"] is False


def test_size_mismatch_is_reported_not_resized() -> None:
    result = compare_images(_solid(2, 2, (0, 0, 0, 255)), _solid(4, 4, (0, 0, 0, 255)))
    assert result["same_size"] is False
    assert result["match"] is False
    # metrics stay internally consistent (every pixel counts as differing)
    assert result["diff_pixels"] == result["total_pixels"]
    assert result["diff_ratio"] == 1.0


def test_invalid_image_raises() -> None:
    with pytest.raises(ImageCompareError):
        compare_images("not-base64!!", _solid(1, 1, (0, 0, 0, 255)))


@pytest.mark.parametrize(
    ("actual", "expected", "op", "want"),
    [
        (5, 5, "==", True),
        (5, 6, "==", False),
        (5, 6, "!=", True),
        (3, 5, "<", True),
        (5, 5, ">=", True),
        ("hello world", "world", "contains", True),
        (1.0000001, 1.0, "approx", True),
        (2.0, 1.0, "approx", False),
        ("x", 1, "<", False),  # TypeError → False, not a crash
        (5, 5, "bogus", False),
    ],
)
def test_evaluate_assertion(actual: object, expected: object, op: str, want: bool) -> None:
    assert evaluate_assertion(actual, expected, op) is want


def test_random_input_events_is_seeded_and_well_formed() -> None:
    a = random_input_events(20, None, seed=7)
    b = random_input_events(20, None, seed=7)
    assert a == b  # deterministic for a given seed
    assert len(a) == 20
    assert all(e["type"] in {"key", "mouse", "action"} for e in a)
    # "click" entries become left mouse-button events
    clicks = random_input_events(5, ["click"], seed=1)
    assert all(e["type"] == "mouse" and e["button"] == "left" for e in clicks)
