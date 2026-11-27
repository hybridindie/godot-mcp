---
name: ship-pr
description: Open or update a PR on GitHub or Gitea, watch CI and review, address review threads, and merge once CI is green and every finding is addressed, if the repo's merge policy allows it.
when_to_use: >
  Run when the user asks to ship, watch, triage, or merge a pull request.
  Trigger phrases: "ship this PR", "open a PR", "watch CI", "address the review",
  "merge when green".
user-invocable: true
---

# Ship PR

<!--
  contract: .claude/rules/doctrine/skill-execution.md
  version: 3.5.0, owner: John D
  invokes: ship-pr/scripts/{forge,watch_pr,pr_threads,pr_size,merge_pr}.py
-->

Open or update a PR, watch CI/review, address findings, and merge if and only
if the gates pass and the repo's merge policy allows it. `--no-merge` stops short.

## Inputs

- Required: a PR number/URL or the current branch. Optional `--no-merge` to
  watch and address threads without merging.
- Forge: from the `origin` remote, as `.agents/scripts/tracker.py` decides it
  (github.com → GitHub via `gh`; any other host → Gitea REST with
  `GITEA_TOKEN` or `TEA_TOKEN`, `GITEA_URL` to override the URL;
  `TRACKER=github|gitea` forces one). tracker.py is the project's own copy,
  rendered with the harness. The scripts
  below hide the difference.
- Merge policy: `merge_policy` in `.claude/harness.json` — `merge`
  (`when-green` default, or `never`), `method` (`merge` default, `squash`,
  `rebase`), `irreversible: "person"` (fixed) and `irreversible_paths` (globs
  added to the pipeline's irreversible lane). Missing means the defaults.
- Read: PR metadata, checks, open findings, and the diff only when a finding
  needs it. Do not read: the whole repository or unrelated PRs.

## Deterministic Steps

Set once: `s=.agents/skills/ship-pr/scripts; [[ -d $s ]] || s=templates/_shared/skills/ship-pr/scripts`
(the second path is genesis itself).

1. **Preflight.** Require `git status` clean and the branch pushed. Confirm the
   PR body links an issue (`Closes #N` or a link). Run `/preflight`; fix failures,
   never bypass a hook. If the project has a pre-review checklist
   (`.claude/rules/doctrine/pre-review-checklist.md`), self-review the diff
   against it before the first push: each push re-runs the review.
2. **Size budget.** Before opening a PR: `python3 "$s/pr_size.py" --base origin/main`
   (git only, so the same on both forges). Exit 1 means over budget
   (`.claude/rules/workflow.md`, step 5): stop and propose a split by layer or
   concern from its `largest` list. Open as one PR only if the caller accepts,
   and then say in the body why it can't be split. Generated files a repo
   commits can be excluded with `--exclude '<glob>'`.
3. **Find the PR.** `python3 "$s/forge.py" find` (exit 1: none for this branch).
4. **Open if missing.** Compose the body from the real change: what/why, verified
   commands, risks/rollback, issue link. Title + body must fit in 2000
   characters (`.claude/rules/workflow.md`, step 5) — check before creating or
   editing, and trim until it passes:
   ```bash
   { printf '%s' "$TITLE"; cat "$BODY_FILE"; } | wc -m   # must be ≤ 2000
   python3 "$s/forge.py" create --base main --title "$TITLE" --body-file "$BODY_FILE"
   ```
   Title format: `<type>(<scope>): <summary>`. Update the body only when scope
   or verification changed, and re-check the length when you do.
5. **Watch.** Run the watcher in the background:
   ```bash
   python3 "$s/watch_pr.py" "$PR" --timeout 1200 > "$(git rev-parse --git-dir)/ship-pr-watch.log" 2>&1 &
   ```
   Exit codes: `0` settled, `10` CI failed, `20` changes requested, `30`
   blocked/draft/conflict, `40` timeout, `50` merged/closed, `2` setup (no
   `gh`, no Gitea token). It never merges. It waits for the configured
   reviewer: `.opencodereview/rule.json` (OpenCodeReview) or `.pr_agent.toml`.
   With neither, it follows a reviewer that already commented on the PR, and
   `SHIP_PR_BOTS=ocr-reviewer` names one outright (`none` disables waiting).
   On Gitea, where the reviewer posts as an ordinary user, always set it. If
   no review lands, ask for one: `python3 "$s/forge.py" comment --pr "$PR" --body /review`.
6. **Fetch open findings.** `python3 "$s/pr_threads.py" --pr "$PR" --json`.
   GitHub: unresolved, non-outdated threads. Gitea (no GraphQL): findings not
   yet answered — resolved, replied to by the PR's author or the token's user
   (in the thread, or a PR comment naming the finding's id), or followed by a
   commit after the review. OpenCodeReview also posts a summary comment
   (`<!-- ocr-summary -->`) whose *Additional findings* are not threads, and
   which names any file it didn't review: read the latest one on the head too.
7. **Triage each.** Real defect → fix + test + rerun preflight, all of the
   round's fixes in one push (re-run the pre-review checklist over them, if
   there is one). Misread →
   reply with evidence. Separate concern → linked follow-up issue + reply.
   Ambiguous → leave open and list for the human. Answer the summary's
   additional findings in one PR comment, one line each (fixed in <sha>, or
   why not); a file it didn't review is a reason to split the PR.
   **Convergence.** A re-review re-reads whole files, so new nits on unchanged
   code are expected. From review cycle 3 on, only findings marked Important
   (`Important —`) block the merge: reply to each Nit with a link to **one**
   follow-up issue that collects them all, then resolve its thread.
8. **Reply and resolve** — only what was handled or rebutted:
   `python3 "$s/pr_threads.py" --pr "$PR" --reply "$ID" --body "$BODY" --resolve`.
   On Gitea the reply carries a marker naming the finding, and lands in the
   PR conversation where the server has no reply endpoint; resolve is skipped
   where it can't (`"resolved": false`), and the reply still answers it.
9. **Loop cap, then escalate.** Repeat watch/fix at most three cycles. A cycle
   fails on failing CI or an Important finding, never on nits alone (step 7).
   After the third failed cycle, do not run a fourth of the same fix, and do
   not stop at a bare report — climb the escalation ladder
   (`.agents/doctrine/escalation.md`, where present):
   1. **Diagnose.** Write a short diagnosis and post it as a PR comment: the
      failing check or thread quoted, what each cycle changed and why it did
      not hold, one cause marked *confirmed* (reproduced, predicted, or read
      from the source) or *suspected*, and the evidence.
   2. **One informed attempt**, only if the cause is confirmed and the fix lies
      inside this PR: make the change it names and watch once more — only once.
   3. **A person.** If the cause is suspected, needs a decision only a person
      can make, or the informed attempt also fails, stop and hand the PR over
      with one specific question and the diagnosis. Never loop again.
10. **Merge through the gate.** With watcher `0`, the review landed and
    preflight green, run `python3 "$s/merge_pr.py" "$PR"` (`--dry-run` under
    `--no-merge`, to report readiness). It reads the policy, then merges if
    and only if: every required check on the head passes (every check when
    none is required; none where the repo defines CI fails), no reviewer
    requests changes, no `Important —` (or unlabelled) finding is open — on
    GitHub no unresolved thread at all — the forge reports it mergeable, it is
    not a draft and has no `do-not-merge` label. It retargets PRs based on the
    head branch to the base first (deleting the branch would close them), then
    merges with the policy's method and deletes the branch. Exits: `0` merged,
    `1` blocked (`blocked_by` lists why: go back to step 5 or 7), `3` ready
    for a person (policy `never`, or an irreversible path: migrations, deploy,
    infra — `.agents/doctrine/agent-plan-schema.md`, "Merge lanes"), `2` setup
    or invalid policy. An ambiguous finding left open blocks it too.
    A retargeted PR `$N` gets no checks on its new base from `pull_request`:
    if the repo defines CI (`.github/workflows/` or `.gitea/workflows/`) and
    `python3 "$s/forge.py" checks --pr "$N"` reports `total` 0, run
    `python3 "$s/forge.py" reopen --pr "$N"` and watch until they run.
    If branch protection needs a human approval, stop and report it. Never use
    `--admin`, a forge's force-merge, or bypass hooks.
    A stack lands via `merge_stack.py <bottom> ... <top>`: all gated, then
    merged bottom-up with merge commits (never squash or rebase a stack).

## LLM Judgment

Use judgment only for:

- classifying a review comment as defect, misread, or separate concern;
- writing the reply/rebuttal;
- deciding whether an ambiguous thread needs the human;
- writing the diagnosis after three failed cycles, and judging its cause.

Do not invent CI results, resolve a thread you did not handle, or merge
around `merge_pr.py`.

## Output

```markdown
PR: <url>    Forge: <github|gitea>
CI: <final state>    Review: <state>    Merge: <commit | ready for a person: <why> | blocked: <why>>
Threads: <fixed> fixed, <rebutted> rebutted, <open> open
Follow-ups: <links or none>
Escalation: <diagnosis link + attempt or question, or none>
```

## Stop Conditions

- Stop if the worktree is dirty, the branch is unpushed, or preflight fails.
- Stop before opening an over-budget PR unless the caller accepts it.
- Stop if the watcher times out or the PR is blocked on a human approval.
- Stop at "ready for a person" when `merge_pr.py` exits `3`; report the reason.
- Stop on a setup error (exit `2`): no `gh`, no Gitea token, or an invalid
  `merge_policy`. If Gitea calls fail to connect while `curl` reaches the
  host, report it: some hosts block Python's network access.
- After three failed review cycles, diagnose; then take at most one informed
  attempt, and otherwise stop with one question for a person (step 9).
- Never merge with a failing or pending check, empty checks where CI exists,
  a missing review, or an open finding; never with `--no-merge`.

## Token Budget

- Read PR metadata, checks and open findings; open the diff or the full
  thread only when a truncated body would make the triage a guess.
- Do not re-fetch the same threads after a push; watch once, then fetch.
- Target ≤ 250 words; use a compact table if there are more than five threads.
- Do not dump full review threads or CI logs.
