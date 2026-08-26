#!/usr/bin/env bash
# Install godot-mcp skills into your AI client's skill directory.
#
# Usage:
#   ./scripts/install-skills.sh                    # opencode (default)
#   ./scripts/install-skills.sh --target ~/.claude/skills  # Claude
#   ./scripts/install-skills.sh --target /custom/path      # custom
#
# Symlinks each skill directory so updates to this repo are picked up
# automatically. Use --copy for a standalone copy instead.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_DIR="$REPO_ROOT/skills"
MODE="symlink"
TARGET="${OPENCODE_SKILLS_DIR:-$HOME/.config/opencode/skills}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --copy)   MODE="copy"; shift ;;
    --symlink) MODE="symlink"; shift ;;
    -h|--help)
      echo "Usage: $0 [--target <dir>] [--copy|--symlink]"
      echo ""
      echo "Install godot-mcp skills into your AI client's skill directory."
      echo ""
      echo "Options:"
      echo "  --target <dir>  Target skill directory (default: ~/.config/opencode/skills)"
      echo "  --copy          Copy files instead of symlinking"
      echo "  --symlink       Symlink (default — repo updates flow through)"
      echo "  -h, --help      Show this help"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [ ! -d "$SKILLS_DIR" ]; then
  echo "Error: no skills/ directory found at $SKILLS_DIR" >&2
  exit 1
fi

mkdir -p "$TARGET"

installed=0
for skill_path in "$SKILLS_DIR"/*/; do
  skill_name="$(basename "$skill_path")"
  dest="$TARGET/$skill_name"

  if [ -e "$dest" ] || [ -L "$dest" ]; then
    echo "  skip: $skill_name (already exists at $dest)"
    continue
  fi

  if [ "$MODE" = "symlink" ]; then
    ln -s "$skill_path" "$dest"
    echo "  link: $skill_name -> $dest"
  else
    cp -R "$skill_path" "$dest"
    echo "  copy: $skill_name -> $dest"
  fi
  installed=$((installed + 1))
done

echo ""
echo "Installed $installed skill(s) to $TARGET"

# List what's available
echo ""
echo "Available skills:"
for skill_path in "$SKILLS_DIR"/*/; do
  skill_name="$(basename "$skill_path")"
  desc=""
  if [ -f "$skill_path/SKILL.md" ]; then
    desc=$(grep -m1 'description:' "$skill_path/SKILL.md" 2>/dev/null | sed 's/description: *//;s/^"//;s/"$//' || true)
  fi
  echo "  $skill_name — $desc"
done