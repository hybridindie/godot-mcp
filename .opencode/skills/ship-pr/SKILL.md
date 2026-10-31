---
name: ship-pr
description: Open or update a PR, watch CI and review, address review threads, and merge only with explicit --merge.
when_to_use: >
  Run when the user asks to ship, watch, triage, or merge a pull request.
  Trigger phrases: "ship this PR", "open a PR", "watch CI", "address the review",
  "merge when green".
user-invocable: true
---

# Ship PR

<!--
  contract: .claude/rules/doctrine/skill-execution.md
  version: 2.0.0, owner: John D
  invokes: ship-pr/scripts/watch_pr.py
-->

Open or update a PR, watch CI/review, address threads, and merge only when the
caller asked for `--merge`.

## Inputs

- Required: a PR number/URL or the current branch; explicit `--merge` to allow
  merging.
- Read: PR metadata, checks, unresolved review threads, and the diff only when a
  thread needs it.
- Do not read: the whole repository or unrelated PRs.

## Deterministic Steps

1. **Preflight.** Require `git status` clean and the branch pushed. Confirm the
   PR body links an issue (`Closes #N` or a link). Run `/preflight`; fix failures,
   never bypass a hook.
2. **Find the PR.**
   ```bash
   gh pr view --json number,url,state 2>/dev/null
   ```
3. **Open if missing.** Compose the body from the real change: what/why, verified
   commands, risks/rollback, issue link. Then:
   ```bash
   gh pr create --base main --title "<type>(<scope>): <summary>" --body-file <file>
   ```
   Update the body only when scope or verification changed.
4. **Watch.** Run the watcher in the background:
   ```bash
   gitdir=$(git rev-parse --git-dir)
   watcher=.claude/skills/ship-pr/scripts/watch_pr.py
   [[ -f $watcher ]] || watcher=templates/_shared/skills/ship-pr/scripts/watch_pr.py
   python3 "$watcher" "$PR" --timeout 1200 > "$gitdir/ship-pr-watch.log" 2>&1 &
   ```
   Exit codes: `0` settled, `10` CI failed, `20` changes requested, `30`
   blocked/draft/conflict, `40` timeout, `50` merged/closed. It never merges.
5. **Fetch unresolved threads.**
   ```bash
   python3 .claude/skills/ship-pr/scripts/pr_threads.py --pr "$PR"
   ```
   The script owns the GraphQL query, repo lookup, and resolved/outdated filter.
6. **Triage each.** Real defect → fix + test + rerun preflight + push. Misread →
   reply with evidence. Separate concern → linked follow-up issue + reply.
   Ambiguous → leave open and list for the human.
7. **Reply and resolve.**
   ```bash
   gh api graphql -f query='
   mutation($thread: ID!, $body: String!) {
     addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $thread, body: $body}) {
       comment { id }
     }
   }' -F thread="$THREAD" -F body="$BODY"
   ```
   Resolve only what was handled or rebutted:
   ```bash
   gh api graphql -f query='
   mutation($thread: ID!) {
     resolveReviewThread(input: {threadId: $thread}) { thread { isResolved } }
   }' -F thread="$THREAD"
   ```
8. **Loop cap.** Repeat watch/fix at most three cycles; then report what remains.
9. **Merge only with `--merge`.** Require preflight green, watcher `0`,
   `mergeStateStatus=CLEAN`, no `CHANGES_REQUESTED`, no unresolved blocking
   thread, and no `do-not-merge` label. Then:
   ```bash
   gh pr merge "$PR" --squash --delete-branch
   ```
   If branch protection needs a human approval, stop and report it. Do not use
   `--admin` or bypass hooks.

## LLM Judgment

Use judgment only for:

- classifying a review comment as defect, misread, or separate concern;
- writing the reply/rebuttal;
- deciding whether an ambiguous thread needs the human.

Do not invent CI results or resolve a thread you did not handle.

## Output

```markdown
PR: <url>
CI: <final state>    Review: <state>    Merge: <commit or not merged>
Threads: <fixed> fixed, <rebutted> rebutted, <open> open
Follow-ups: <links or none>
```

## Stop Conditions

- Stop if the worktree is dirty, the branch is unpushed, or preflight fails.
- Stop if the watcher times out or the PR is blocked on a human approval.
- Stop after three review cycles and report the remaining threads.
- Never merge without the caller's explicit `--merge`.

## Token Budget

- Default: read PR metadata, checks, and unresolved threads; open the diff for a
  thread only when needed. Read the full thread when a truncated body would make
  the triage a guess.
- Do not re-fetch the same threads after a push; watch once, then fetch.
- Target ≤ 250 words; use a compact table if there are more than five threads.
- Do not dump full review threads or CI logs.
