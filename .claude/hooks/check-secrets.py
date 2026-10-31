#!/usr/bin/env python3
"""Scan staged or tracked files for credentials before they leave the machine.

Usage:
  python3 .claude/hooks/check-secrets.py --staged
  python3 .claude/hooks/check-secrets.py --all
  python3 .claude/hooks/check-secrets.py path/to/file [...]

Exits 1 when a likely secret is found. False positives can be allowed with an
inline `allowlist secret`, `gitleaks:allow`, or `pragma: allowlist secret`
comment. This is a guardrail, not a replacement for a dedicated scanner; it is
deliberately dependency-free so it works in every profile.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".godot",
    "graphify-out",
}
SKIP_NAMES = {
    ".env.example",
    ".env.sample",
    ".env.template",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "uv.lock",
    "poetry.lock",
}
SKIP_SUFFIXES = {".lock", ".min.js", ".map", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip"}
MAX_BYTES = 1_000_000
ALLOW = re.compile(
    r"allowlist secret|gitleaks:allow|pragma: allowlist secret|nosec",
    re.IGNORECASE,
)
ALLOW_VALUES = re.compile(
    r"example|dummy|fake|placeholder|changeme|your[_-]|redacted|\.\.\.|\$\{|<[^>]+>",
    re.IGNORECASE,
)

PATTERNS = [
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}\b")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("OpenAI key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("Stripe key", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("generic secret", re.compile(
        r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|client[_-]?secret)\b"
        r"\s*[:=]\s*[\"'][^\"'\s]{16,}[\"']"
    )),
    ("dotenv secret", re.compile(
        r"(?im)^[A-Z0-9_]*(?:SECRET|TOKEN|KEY|PASSWORD)[A-Z0-9_]*\s*=\s*[^\s#]{16,}\s*$"
    )),
]

def is_text(path: Path) -> bool:
    try:
        if path.stat().st_size > MAX_BYTES:
            return False
        chunk = path.read_bytes()[:8192]
    except OSError:
        return False
    return b"\x00" not in chunk

def should_skip(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return True
    if path.name in SKIP_NAMES or path.suffix in SKIP_SUFFIXES:
        return True
    return False

def redact(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"

def scan_text(text: str, label: str, findings: list[str]) -> None:
    for lineno, line in enumerate(text.splitlines(), 1):
        if ALLOW.search(line):
            continue
        for name, pattern in PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            value = match.group(0)
            if name in {"generic secret", "dotenv secret"} and ALLOW_VALUES.search(value):
                continue
            findings.append(f"SECRET: {label}:{lineno} ({name}) {redact(value)}")
            break

def git_files(staged: bool) -> list[str]:
    args = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]
    if not staged:
        args = ["git", "ls-files", "--cached", "--others", "--exclude-standard"]
    try:
        out = subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return []
    return [line for line in out.splitlines() if line.strip()]

def read_staged(path: str) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "show", f":{path}"], stderr=subprocess.DEVNULL
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    if len(out) > MAX_BYTES:
        return None
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError:
        return None

def main() -> int:
    parser = argparse.ArgumentParser(description="Scan for credentials")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--staged", action="store_true", help="scan staged files")
    group.add_argument("--all", action="store_true", help="scan tracked and untracked files")
    parser.add_argument("--quiet", action="store_true", help="print nothing on success")
    parser.add_argument("paths", nargs="*", help="explicit files to scan")
    args = parser.parse_args()

    findings: list[str] = []
    scanned = 0

    if args.paths:
        for raw in args.paths:
            path = Path(raw)
            if path.is_file() and not should_skip(path) and is_text(path):
                scan_text(path.read_text(encoding="utf-8", errors="replace"), raw, findings)
                scanned += 1
    else:
        staged = args.staged or not args.all
        for raw in git_files(staged):
            path = Path(raw)
            if should_skip(path):
                continue
            if staged:
                text = read_staged(raw)
                if text is None:
                    continue
            else:
                if not path.is_file() or not is_text(path):
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            scan_text(text, raw, findings)
            scanned += 1

    for finding in findings:
        print(finding)
    if findings:
        print(f"FAIL: {len(findings)} potential secret(s) found. Remove and rotate them.")
        return 1
    if not args.quiet:
        print(f"PASS: no secrets in {scanned} file(s)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
