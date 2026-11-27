#!/usr/bin/env python3
"""A per-Epic token ledger, so a run can warn and pause before it overspends.

  budget.py record --epic N --unit U --tokens T [--limit L]
  budget.py status --epic N [--limit L]
  budget.py reset --epic N

N is an Epic number (`12` or `#12`). U is the unit that spent the tokens, such
as `S1/A`. `status` prints {"used", "limit", "percent", "state"}: state is `ok`
below 80% of the limit, `warn` from 80% and `pause` from 100%. The default
limit is 5,000,000 tokens; percent is rounded down to a whole number.

Every command prints JSON on stdout and exits 0 on success, 2 on bad input or
an environment error (not in a git repository, unreadable ledger).

The ledger is `<git common dir>/agent-plan/budget.json`, beside dispatch.py's
state, so every worktree of a repository shares it. Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime
import fcntl
import json
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

DEFAULT_LIMIT = 5_000_000
WARN_PERCENT = 80


class BudgetError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    """argparse, but usage errors are JSON on stdout with exit 2 like the rest."""

    def error(self, message: str):  # type: ignore[override]
        print(json.dumps({"ok": False, "error": message}, indent=2))
        raise SystemExit(2)


# ── ledger ───────────────────────────────────────────────────────────────────

def work_dir() -> Path:
    run = subprocess.run(["git", "rev-parse", "--git-common-dir"], capture_output=True, text=True)
    if run.returncode != 0:
        raise BudgetError(f"not in a git repository: {run.stderr.strip()}")
    common = Path(run.stdout.strip())
    if not common.is_absolute():
        common = (Path.cwd() / common).resolve()
    return common / "agent-plan"


def is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def check_entry(path: Path, i: int, entry) -> None:
    """Refuse an entry that would crash the totals, naming it."""
    if not isinstance(entry, dict):
        problem = "is not an object"
    elif not is_int(entry.get("epic")):
        problem = "has no whole-number epic"
    elif not is_int(entry.get("tokens")) or entry["tokens"] < 0:
        problem = "has no non-negative whole-number tokens"
    else:
        return
    raise BudgetError(f"{path} entry {i} {problem}: {json.dumps(entry)}")


@contextmanager
def ledger():
    """Yield the ledger dict under an exclusive lock and write it back atomically."""
    d = work_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / "budget.json"
    with open(d / "budget.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            try:
                data = json.loads(path.read_text())
            except ValueError as exc:
                raise BudgetError(f"{path} is not valid JSON: {exc}") from exc
            if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
                raise BudgetError(f"{path} has no entries list")
            for i, entry in enumerate(data["entries"]):
                check_entry(path, i, entry)
        else:
            data = {"version": 1, "entries": []}
        before = json.dumps(data, sort_keys=True)
        yield data
        if json.dumps(data, sort_keys=True) != before:
            fd, tmp = tempfile.mkstemp(dir=d, prefix=".budget.", suffix=".json")
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.replace(tmp, path)


def used(data: dict, epic: int) -> int:
    return sum(int(e.get("tokens", 0)) for e in data["entries"] if e.get("epic") == epic)


def summary(total: int, limit: int) -> dict:
    if total * 100 >= limit * 100:
        state = "pause"
    elif total * 100 >= limit * WARN_PERCENT:
        state = "warn"
    else:
        state = "ok"
    return {"used": total, "limit": limit, "percent": total * 100 // limit, "state": state}


# ── commands ─────────────────────────────────────────────────────────────────

def cmd_record(args) -> dict:
    with ledger() as data:
        data["entries"].append({
            "epic": args.epic, "unit": args.unit, "tokens": args.tokens,
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        })
        total = used(data, args.epic)
    return {"epic": args.epic, "unit": args.unit, "tokens": args.tokens, **summary(total, args.limit)}


def cmd_status(args) -> dict:
    with ledger() as data:
        total = used(data, args.epic)
    return summary(total, args.limit)


def cmd_reset(args) -> dict:
    with ledger() as data:
        keep = [e for e in data["entries"] if e.get("epic") != args.epic]
        removed = len(data["entries"]) - len(keep)
        data["entries"] = keep
    return {"epic": args.epic, "removed": removed}


# ── argument types ───────────────────────────────────────────────────────────

def epic_number(value: str) -> int:
    text = value.strip().removeprefix("#")
    # ASCII digits only: isdigit() passes "²" (which int() rejects) and
    # isdecimal() passes "٧" (which int() reads as 7).
    if not re.fullmatch(r"[0-9]+", text) or int(text) <= 0:
        raise argparse.ArgumentTypeError(f"not an Epic number: {value!r}")
    return int(text)


def non_negative(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number: {value!r}") from None
    if n < 0:
        raise argparse.ArgumentTypeError(f"must not be negative: {value}")
    return n


def positive(value: str) -> int:
    n = non_negative(value)
    if n == 0:
        raise argparse.ArgumentTypeError("must be positive")
    return n


def unit_name(value: str) -> str:
    if not value.strip():
        raise argparse.ArgumentTypeError("must not be empty")
    return value.strip()


def main(argv: list[str] | None = None) -> int:
    ap = Parser(description="Per-Epic token ledger.")
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=Parser)
    p = sub.add_parser("record", help="append a spend entry")
    p.add_argument("--epic", type=epic_number, required=True)
    p.add_argument("--unit", type=unit_name, required=True)
    p.add_argument("--tokens", type=non_negative, required=True)
    p.add_argument("--limit", type=positive, default=DEFAULT_LIMIT)
    p = sub.add_parser("status", help="print used, limit, percent and state")
    p.add_argument("--epic", type=epic_number, required=True)
    p.add_argument("--limit", type=positive, default=DEFAULT_LIMIT)
    p = sub.add_parser("reset", help="clear an Epic's entries")
    p.add_argument("--epic", type=epic_number, required=True)
    args = ap.parse_args(argv)
    try:
        result = globals()[f"cmd_{args.cmd}"](args)
    except (BudgetError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
