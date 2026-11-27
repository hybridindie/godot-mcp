#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Ask a second model, through `opencode run`, whether a plan is ready.

  plan_review.py <plan-file>... [--model M] [--round N --prior <json>]
                 [--health-timeout 30] [--timeout 300]

First a one-line health prompt checks that the model answers at all, within
--health-timeout seconds. Then the review prompt goes out with the plan files
attached (`--file`) and the matching rubric (`.agents/evals/epic-rubric.md`
and/or `story-rubric.md`) inlined, asking for JSON
`{"verdict": "ready"|"needs-work"|"blocked", "findings": [{"severity", "text"}]}`.

Each finding is "blocking" (contradictions, unverifiable criteria, ownership
gaps or overlaps, scope or decision conflicts, an impossible dependency order)
or "deferred" (task granularity, missing task lists, task-level verify
strictness, wording: work for task-decomposer). For ready and needs-work the
verdict follows the blocking findings: with none left it is "ready", whatever
the model said. A "blocked" answer passes through, every finding a question
for a person.

From round 2 (`--round 2 --prior <json>`), the prompt carries the previous
round's blocking findings and the author's answers, a JSON list of
`{"finding", "answer"}` given inline or as a file, and asks the model to judge
whether each is resolved and to raise only new blocking findings.

An answer with no valid verdict JSON (often one cut off mid-object) is retried
once with a "JSON only" nudge before the run counts as unreviewed.

The reviewer only reads: `--auto` is never passed, so it cannot be granted
write or shell permissions.

The model is --model, else $PLAN_REVIEW_MODEL, else opencode/big-pickle (a free
OpenCode Zen model that needs no provider setup but may be retired). Set
PLAN_REVIEW_MODEL to a model other than the one that wrote the plan: the point
is a second reader.

Prints JSON `{"verdict", "findings", "deferred", "model", "round"}` on stdout;
"findings" holds the blocking findings (or a blocked verdict's questions) and
"deferred" the rest, as strings. Exit codes:
  0 ready   1 needs-work   2 blocked
  3 couldn't review (health check failed, timeout, unparseable answer twice,
    bad arguments). The verdict is then "unreviewed" and "error" says why; a
    couldn't-review result is never ready.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS = HERE.parent / "evals"
DEFAULT_MODEL = "opencode/big-pickle"
VERDICTS = {"ready": 0, "needs-work": 1, "blocked": 2}
SEVERITIES = ("blocking", "deferred")
UNREVIEWED = 3

HEALTH_PROMPT = "Reply with exactly: OK"
KIND = re.compile(r"^kind:[ \t]*['\"]?(epic|story)\b", re.MULTILINE)

INSTRUCTION = """\
You are reviewing an implementation plan before any work is dispatched. \
The plan files are attached. Read them only; do not edit anything or run commands.

Judge the plan against the rubric below. A finding is one concrete problem, \
naming where it is and what to change, with a severity:

- "blocking": the plan cannot be dispatched as written. Only these: the Epic and \
its stories contradict each other; an acceptance criterion cannot be verified or \
observed; two units own the same file, or a file the work must change is owned \
by none; scope or a recorded decision conflicts; the dependency order cannot work.
- "deferred": everything task-level, which the task-decomposer step after this \
review fills in: task granularity, a missing task list, how strict a task's \
verify command is, wording. Never hold a plan back for these.

Answer with one JSON object and nothing else:
{"verdict": "ready" | "needs-work" | "blocked", \
"findings": [{"severity": "blocking" | "deferred", "text": "..."}]}

- "ready": no blocking finding; list any deferred ones.
- "needs-work": at least one blocking finding the author can fix; list every finding.
- "blocked": it cannot proceed without a human decision; say which.
"""

FOLLOW_UP = """
This is review round {round}. The author revised the plan after the previous \
round's blocking findings, listed below with their answers. For each, judge \
whether the revised plan resolves it; raise an unresolved one again as blocking, \
quoting it. Do not repeat a resolved finding. Raise a new finding only if it is \
blocking: anything task-level goes to task-decomposer, not to another round.

Prior findings:
{prior}
"""

RETRY = """
Your previous answer had no complete JSON verdict (it may have been cut off). \
Reply with the JSON object only: no prose, no code fence, short findings.
"""


class ReviewError(Exception):
    """The plan could not be reviewed (exit 3)."""


class AnswerError(ReviewError):
    """The model answered, but not with a valid verdict; worth one retry."""


class Parser(argparse.ArgumentParser):
    def error(self, message):  # exit 2 means "blocked" here, so usage errors are 3
        raise ReviewError(f"usage: {message}")


def positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise ValueError(value)
    return n


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise ReviewError(f"cannot read {path}: {e}") from e


def rubrics(plans: list[Path]) -> str:
    kinds: set[str] = set()
    for p in plans:
        kinds.update(KIND.findall(read(p)))
    if not kinds:
        kinds = {"epic", "story"}
    parts = []
    for kind in sorted(kinds):
        path = EVALS / f"{kind}-rubric.md"
        if not path.is_file():
            raise ReviewError(f"rubric not found: {path}")
        parts.append(f"## {kind.capitalize()} rubric\n\n{read(path)}")
    return "\n\n".join(parts)


def load_prior(value: str) -> list[dict]:
    """The previous round's findings and answers: inline JSON or a JSON file."""
    text = value if value.lstrip().startswith("[") else read(Path(value))
    try:
        prior = json.loads(text)
    except json.JSONDecodeError as e:
        raise ReviewError(f"--prior is not JSON: {e}") from None
    ok = isinstance(prior, list) and prior and all(
        isinstance(p, dict) and isinstance(p.get("finding"), str) and p["finding"].strip()
        and isinstance(p.get("answer", ""), str) for p in prior)
    if not ok:
        raise ReviewError('--prior must be a non-empty list of {"finding", "answer"}')
    return prior


def follow_up(round_: int, prior: list[dict]) -> str:
    lines = [f"{n}. {p['finding']}\n   Answer: {p.get('answer') or '(none given)'}"
             for n, p in enumerate(prior, 1)]
    return FOLLOW_UP.format(round=round_, prior="\n".join(lines))


def run_opencode(prompt: str, model: str, files: list[Path], timeout: float) -> str:
    """Run one `opencode run` and return the text of the final assistant message."""
    cmd = ["opencode", "run", prompt, "--archived", "--format", "json", "--model", model]
    for f in files:
        cmd += ["--file", str(f)]
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
                                start_new_session=True)
    except OSError as e:
        raise ReviewError(f"cannot run opencode: {e}") from e
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        proc.communicate()
        raise ReviewError(f"opencode timed out after {timeout:g}s") from None
    events = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    errors = [e for e in events if e.get("type") == "error"]
    if proc.returncode != 0 or errors:
        detail = json.dumps(errors[-1].get("error", errors[-1])) if errors else err.strip()[-500:]
        raise ReviewError(f"opencode failed (exit {proc.returncode}): {detail}")
    texts = [(e.get("part") or {}) for e in events if e.get("type") == "text"]
    texts = [p for p in texts if isinstance(p.get("text"), str)]
    if not texts:
        raise ReviewError("opencode returned no text")
    last = texts[-1].get("messageID")
    return "".join(p["text"] for p in texts if p.get("messageID") == last)


def parse_verdict(text: str) -> tuple[str, list[str], list[str]]:
    """Find the reviewer's JSON object in its answer; the last valid one wins.
    Returns the verdict, the blocking findings and the deferred ones."""
    decoder = json.JSONDecoder()
    found = None
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "verdict" in obj:
            found = obj
    if found is None:
        raise AnswerError(f"no verdict JSON in the answer: {text.strip()[:300]!r}")
    verdict = found.get("verdict")
    findings = found.get("findings", [])
    if not isinstance(verdict, str) or verdict not in VERDICTS:
        raise AnswerError(f"unknown verdict {verdict!r}")
    if not isinstance(findings, list) or not all(
            isinstance(f, dict) and f.get("severity") in SEVERITIES
            and isinstance(f.get("text"), str) and f["text"].strip() for f in findings):
        raise AnswerError('findings is not a list of {"severity": "blocking"|"deferred", "text"}')
    if verdict != "ready" and not findings:
        raise AnswerError(f"verdict {verdict} with no findings")
    blocking = [f["text"] for f in findings if f["severity"] == "blocking"]
    deferred = [f["text"] for f in findings if f["severity"] == "deferred"]
    if verdict == "blocked":  # a human decision: every finding is its question
        return verdict, blocking + deferred, []
    return ("needs-work" if blocking else "ready"), blocking, deferred


def review(argv: list[str]) -> tuple[dict, int]:
    ap = Parser(prog="plan_review.py", description="Review plan files with a second model.")
    ap.add_argument("plans", nargs="+", metavar="plan-file")
    ap.add_argument("--model", default=os.environ.get("PLAN_REVIEW_MODEL") or DEFAULT_MODEL)
    ap.add_argument("--round", type=positive_int, default=1, dest="round_")
    ap.add_argument("--prior", help='JSON list of {"finding", "answer"}, inline or a file')
    ap.add_argument("--health-timeout", type=float, default=30)
    ap.add_argument("--timeout", type=float, default=300)
    model = os.environ.get("PLAN_REVIEW_MODEL") or DEFAULT_MODEL
    round_ = 1
    try:
        args = ap.parse_args(argv)
        model, round_ = args.model, args.round_
        if (round_ > 1) != (args.prior is not None):
            raise ReviewError("--round 2 or later and --prior go together")
        plans = [Path(p).resolve() for p in args.plans]
        missing = [str(p) for p in plans if not p.is_file()]
        if missing:
            raise ReviewError(f"plan file not found: {', '.join(missing)}")
        prompt = f"{INSTRUCTION}\n{rubrics(plans)}\n"
        if args.prior is not None:
            prompt += follow_up(round_, load_prior(args.prior))
        try:
            if not run_opencode(HEALTH_PROMPT, model, [], args.health_timeout).strip():
                raise ReviewError("empty answer")
        except ReviewError as e:
            raise ReviewError(f"health check failed (set PLAN_REVIEW_MODEL or --model): {e}") from None
        try:
            answer = parse_verdict(run_opencode(prompt, model, plans, args.timeout))
        except AnswerError:
            try:
                answer = parse_verdict(run_opencode(prompt + RETRY, model, plans, args.timeout))
            except AnswerError as e:
                raise ReviewError(f"{e} (also after a JSON-only retry)") from None
        verdict, findings, deferred = answer
    except ReviewError as e:
        return {"verdict": "unreviewed", "findings": [], "deferred": [], "model": model,
                "round": round_, "error": str(e)}, UNREVIEWED
    return {"verdict": verdict, "findings": findings, "deferred": deferred, "model": model,
            "round": round_}, VERDICTS[verdict]


def main(argv: list[str] | None = None) -> int:
    result, code = review(sys.argv[1:] if argv is None else argv)
    print(json.dumps(result, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
