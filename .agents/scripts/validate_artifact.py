#!/usr/bin/env python3
"""Validate the prose shape of Epic and story bodies, and extract their ACs.

The plan itself (stories, tracks, tasks, ownership, waves) lives in the
`agent-plan` block and is checked by `.agents/scripts/plan.py validate`; this
script only checks the human-facing sections and that the block is present.

Usage:
  python3 .agents/scripts/validate_artifact.py --kind epic <file>
  python3 .agents/scripts/validate_artifact.py --kind story <file>
  python3 .agents/scripts/validate_artifact.py --kind acceptance <file>
  ... --summary      print one line of counts and gaps; always exit 0

Exit 0 on a valid shape. Semantic quality remains the skill's LLM judgment.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

AC = re.compile(r"^\s*[-*]\s*(?:\*\*)?(AC\d+)(?:\*\*)?[:\s]", re.MULTILINE)
# A checkbox criterion: `- [ ] **Given** …`, optionally labelled `**AC1:**`,
# with or without bold on Given.
AC_BOX = re.compile(r"^\s*-\s*\[[ xX]\]\s*(?:\*\*(AC\d+):?\*\*:?\s*)?(?:\*\*)?Given\b", re.MULTILINE)
PLAN_BLOCK = re.compile(r"^```ya?ml[ \t]+agent-plan[ \t]*$", re.MULTILINE)
EPIC_LABELS = [
    "**Why**",
    "**Outcome**",
    "**Scope**",
    "**Acceptance criteria**",
    "**Constraints",
    "**Risks",
    "**Success measures**",
    "**Definition of done**",
]
STORY_LABELS = [
    "**Context**",
    "**Acceptance criteria**",
    "**Done when**",
]


def read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


PLAN_FENCE = re.compile(r"^```ya?ml[ \t]+agent-plan[ \t]*\n.*?^```[ \t]*$", re.MULTILINE | re.DOTALL)


def prose(text: str) -> str:
    """The body without its agent-plan block: list items such as `- AC1` inside
    the YAML are plan data, not criteria."""
    return PLAN_FENCE.sub("", text.replace("\r\n", "\n"))


def count_ac(text: str) -> int:
    text = prose(text)
    return len(AC.findall(text)) + len(AC_BOX.findall(text))


def plan_blocks(text: str) -> list[str]:
    text = text.replace("\r\n", "\n")
    n = len(PLAN_BLOCK.findall(text))
    if n == 0:
        return ["no ```yaml agent-plan block"]
    if n > 1:
        return [f"{n} agent-plan blocks; keep exactly one"]
    if not PLAN_FENCE.search(text):  # an open fence alone would leak plan data into the prose
        return ["the agent-plan block is not closed with ```"]
    return []


def check_epic(text: str) -> list[str]:
    errors = [f"missing {label}" for label in EPIC_LABELS if label not in text]
    acs = count_ac(text)
    if not 3 <= acs <= 8:
        errors.append(f"acceptance criteria count {acs} is outside 3–8")
    return errors + plan_blocks(text)


def check_story(text: str) -> list[str]:
    errors = [f"missing {label}" for label in STORY_LABELS if label not in text]
    if "**As a**" not in text and "**What**" not in text:
        errors.append("missing user-story frame (As a / What)")
    if "Part of #" not in text:
        errors.append("missing Part of #<epic>")
    if count_ac(text) < 1:
        errors.append("no acceptance criteria")
    return errors + plan_blocks(text)


def extract_acceptance(text: str) -> list[tuple[str, str]]:
    """AC-labelled lines (epics) and Given/When/Then checkboxes (stories)."""
    found: list[tuple[str, str]] = []
    text = prose(text)
    boxes = 0
    lines = text.splitlines()
    for i, line in enumerate(lines):
        match = re.match(r"^\s*[-*]\s*(?:\*\*)?(AC\d+)(?:\*\*)?[:\s-]+(.*)$", line)
        if match:
            found.append((match.group(1), match.group(2).lstrip("*: -").strip()))
        elif box := AC_BOX.match(line):
            boxes += 1
            parts = [re.sub(r"^\s*-\s*\[[ xX]\]\s*", "", line)]
            indent = len(line) - len(line.lstrip())
            # A wrapped criterion continues on more-indented, non-list lines.
            for nxt in lines[i + 1:]:
                if not nxt.strip() or len(nxt) - len(nxt.lstrip()) <= indent \
                        or re.match(r"^\s*[-*]\s", nxt):
                    break
                parts.append(nxt.strip())
            body = re.sub(r"^(?:AC\d+:?\s*)", "", " ".join(parts).replace("**", "").strip())
            found.append((box.group(1) or f"AC{boxes}", body))
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("epic", "story", "acceptance"), required=True)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("path", help="artifact path, or - for stdin")
    args = parser.parse_args()
    text = read(args.path)

    if args.kind == "acceptance":
        criteria = extract_acceptance(text)
        if args.summary:
            weak = sum(1 for _, b in criteria if not re.search(r"\bwhen\b.*\bthen\b", b, re.I))
            print(f"acceptance: criteria={len(criteria)} weak={weak}")
            return 0
        if not criteria:
            print("FAIL: no acceptance criteria found (ACn lines or Given/When/Then checkboxes)", file=sys.stderr)
            return 1
        for label, body in criteria:
            weak = "" if re.search(r"\bwhen\b.*\bthen\b", body, re.I) else " (weak: no when/then)"
            print(f"{label}\t{body}{weak}")
        print(f"PASS: {len(criteria)} acceptance criteria extracted")
        return 0

    if args.kind == "epic":
        errors = check_epic(text)
        summary = f"ACs={count_ac(text)}"
    else:
        errors = check_story(text)
        summary = f"ACs={count_ac(text)}"

    if args.summary:
        gaps = "; ".join(errors) if errors else "none"
        print(f"{args.kind}: {summary} gaps={len(errors)} ({gaps})")
        return 0
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: {args.kind} shape ({summary})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
