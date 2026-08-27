#!/usr/bin/env python3
"""Reset the godot/ project to a clean state after eval runs.

Removes eval artifacts (tmp_e2e*, eval_*, play_test.gd, etc.), restores tracked
files from git, and clears the .godot cache so the editor starts fresh.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GODOT_DIR = REPO_ROOT / "godot"

# Patterns of eval-created files to remove
PATTERNS = [
    "tmp_e2e*",
    "eval_test*.gd",
    "eval_test*.gd.uid",
    "play_test.gd",
    "play_test.gd.uid",
    "char_test.gd",
    "char_test.gd.uid",
]

# Directories where eval scripts/scenes are typically created
SEARCH_DIRS = [
    GODOT_DIR,
    GODOT_DIR / "scripts",
    GODOT_DIR / "scenes",
    GODOT_DIR / "shaders",
]


def remove_artifacts() -> int:
    removed = 0
    for directory in SEARCH_DIRS:
        if not directory.exists():
            continue
        for pattern in PATTERNS:
            for path in directory.glob(pattern):
                try:
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    removed += 1
                    print(f"  Removed: {path.relative_to(REPO_ROOT)}")
                except OSError as exc:
                    print(f"  Failed to remove {path}: {exc}", file=sys.stderr)
    return removed


def git_restore() -> None:
    """Restore tracked files in godot/ from git HEAD."""
    print("Restoring tracked files in godot/ from git HEAD...")
    result = subprocess.run(
        ["git", "checkout", "HEAD", "--", "godot/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"git checkout warning: {result.stderr}", file=sys.stderr)
    else:
        print("  Tracked files restored.")


def clear_godot_cache() -> None:
    cache_dir = GODOT_DIR / ".godot"
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
        print(f"  Cleared: {cache_dir.relative_to(REPO_ROOT)}")


def main() -> int:
    print("Resetting godot/ project...")
    removed = remove_artifacts()
    git_restore()
    clear_godot_cache()
    if removed:
        print(f"Done. Removed {removed} eval artifact(s).")
    else:
        print("Done. No artifacts found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
