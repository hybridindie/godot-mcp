"""QA / play-testing logic (issue #37).

Pure, bridge-free helpers used by the testing tools: image comparison (perceptual-ish
per-pixel diff), assertion evaluation, and random-input generation. Kept out of the tool
handlers per Article I (handlers delegate; logic lives here).
"""

from __future__ import annotations

import base64
import binascii
import io
import random
from typing import Any

import png


class ImageCompareError(ValueError):
    """Raised when an image cannot be decoded for comparison."""


def _decode_rgba(data_b64: str) -> tuple[int, int, list[int]]:
    """Decode a base64 PNG into (width, height, flat RGBA8 byte list)."""
    raw = data_b64.split(",", 1)[-1].strip()  # tolerate a data: URI prefix
    try:
        blob = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ImageCompareError(f"not valid base64: {exc}") from exc
    try:
        width, height, rows, _info = png.Reader(bytes=blob).asRGBA8()
        flat = [channel for row in rows for channel in row]
    except (png.Error, ValueError) as exc:
        raise ImageCompareError(f"not a decodable PNG: {exc}") from exc
    return width, height, flat


def compare_images(a_b64: str, b_b64: str, tolerance: float = 0.0) -> dict[str, Any]:
    """Compare two base64 PNGs. ``tolerance`` (0..1) is the per-channel difference a pixel
    may have before it counts as "different" (as a fraction of 255).

    Returns same_size / dimensions / diff_pixels / total_pixels / diff_ratio /
    mean_abs_diff (0..1) / match (true when no pixel differs beyond tolerance and sizes
    match). Different-sized images are reported, not resized.
    """
    tolerance = max(0.0, min(1.0, tolerance))  # documented 0..1; guard against >1 matching all
    aw, ah, a = _decode_rgba(a_b64)
    bw, bh, b = _decode_rgba(b_b64)
    if (aw, ah) != (bw, bh):
        total = aw * ah
        return {
            "same_size": False,
            "width": aw,
            "height": ah,
            "diff_pixels": total,  # incomparable → treat every pixel as differing
            "total_pixels": total,
            "diff_ratio": 1.0,
            "mean_abs_diff": 1.0,
            "match": False,
        }
    threshold = tolerance * 255
    total_pixels = aw * ah
    diff_pixels = 0
    abs_sum = 0
    for i in range(0, len(a), 4):
        pixel_differs = False
        for c in range(4):
            delta = abs(a[i + c] - b[i + c])
            abs_sum += delta
            if delta > threshold:
                pixel_differs = True
        if pixel_differs:
            diff_pixels += 1
    channels = max(1, len(a))
    return {
        "same_size": True,
        "width": aw,
        "height": ah,
        "diff_pixels": diff_pixels,
        "total_pixels": total_pixels,
        "diff_ratio": diff_pixels / total_pixels if total_pixels else 0.0,
        "mean_abs_diff": abs_sum / channels / 255,
        "match": diff_pixels == 0,
    }


# Comparison operators for assert_node_state, kept explicit (no eval).
def evaluate_assertion(actual: Any, expected: Any, op: str) -> bool:
    """Evaluate ``actual <op> expected``. Supports ==, !=, <, <=, >, >=, contains, approx
    (float within 1e-6 + relative). Unknown ops return False.
    """
    try:
        match op:
            case "==":
                return bool(actual == expected)
            case "!=":
                return bool(actual != expected)
            case "<":
                return bool(actual < expected)
            case "<=":
                return bool(actual <= expected)
            case ">":
                return bool(actual > expected)
            case ">=":
                return bool(actual >= expected)
            case "contains":
                return expected in actual
            case "approx":
                return abs(float(actual) - float(expected)) <= 1e-6 + 1e-6 * abs(float(expected))
    except (TypeError, ValueError):
        return False
    return False


# Default fuzz action pool: common keys + a mouse click marker.
_DEFAULT_FUZZ_ACTIONS = ["ui_left", "ui_right", "ui_up", "ui_down", "Space", "Enter", "click"]


def random_input_events(
    count: int, actions: list[str] | None, seed: int, width: int = 1152, height: int = 648
) -> list[dict[str, Any]]:
    """Build ``count`` random input events from ``actions`` (key names, input-map action
    names, or "click"), seeded for reproducibility. "click" → a left mouse button at a
    random viewport point; a name with no spaces and lowercase-with-underscores is treated
    as an input-map action, otherwise a key.
    """
    pool = actions or _DEFAULT_FUZZ_ACTIONS
    rng = random.Random(seed)
    events: list[dict[str, Any]] = []
    for _ in range(count):
        choice = rng.choice(pool)
        if choice == "click":
            events.append(
                {
                    "type": "mouse",
                    "x": rng.randint(0, max(0, width - 1)),  # randint upper bound is inclusive
                    "y": rng.randint(0, max(0, height - 1)),
                    "button": "left",
                    "pressed": True,
                }
            )
        elif "_" in choice and choice.islower():
            events.append(
                {"type": "action", "action": choice, "pressed": rng.choice([True, False])}
            )
        else:
            events.append({"type": "key", "key": choice, "pressed": rng.choice([True, False])})
    return events


def encode_png(width: int, height: int, rows: list[list[int]]) -> str:
    """Encode RGBA8 ``rows`` into a base64 PNG (used by tests to build fixtures)."""
    buffer = io.BytesIO()
    png.Writer(width=width, height=height, greyscale=False, alpha=True).write(buffer, rows)
    return base64.b64encode(buffer.getvalue()).decode("ascii")
