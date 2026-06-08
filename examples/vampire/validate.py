#!/usr/bin/env python3
"""Validate the Vampire Survivors demo scene and scripts.

Usage (from repo root):
    uv run python examples/vampire/validate.py /path/to/godot-bin

Requires Godot 4.4+ with --check-only and --headless.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent


def validate(godot_bin: Path) -> int:
    if not godot_bin.exists():
        print(f"ERROR: Godot binary not found: {godot_bin}")
        return 1

    print(f"Validating Vampire Survivors demo in {DEMO_DIR} ...")

    result = subprocess.run(
        [
            str(godot_bin),
            "--headless",
            "--path", str(DEMO_DIR),
            "--check-only",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print("Demo validation PASSED")
        return 0
    else:
        print("Demo validation FAILED")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        return result.returncode


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate Vampire Survivors demo")
    parser.add_argument(
        "godot_bin",
        nargs="?",
        default="godot",
        help="Path to Godot binary (default: 'godot' in PATH)",
    )
    args = parser.parse_args()
    sys.exit(validate(Path(args.godot_bin)))
