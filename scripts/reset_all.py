#!/usr/bin/env python3
"""Reset both the godot/ project and the examples/vampire/ scene.

Convenience wrapper that runs both individual reset scripts in sequence.
Use this before a fresh eval run to ensure a clean starting state.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent


def run_reset(script_name: str) -> int:
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        print(f"Missing reset script: {script_path}", file=sys.stderr)
        return 1
    print(f"\n{'=' * 60}")
    print(f"Running {script_name}...")
    print("=" * 60)
    result = subprocess.run([sys.executable, str(script_path)], check=False)
    return result.returncode


def main() -> int:
    rc = run_reset("reset_godot_project.py")
    if rc != 0:
        return rc
    rc = run_reset("reset_vampire_example.py")
    return rc


if __name__ == "__main__":
    sys.exit(main())
