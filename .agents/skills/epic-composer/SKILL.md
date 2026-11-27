---
name: epic-composer
description: >
  Draft an Epic issue from source material that both people and AI agents can work from:
  one outcome, 3–8 observable acceptance criteria, explicit scope, and a validated
  agent-plan block listing stories with file ownership, dependencies and verify
  commands, from which parallel waves are computed. Trigger phrases: "compose an epic",
  "draft an epic", "scope new work", "plan this feature for agents", "turn these notes
  into an epic", "write an epic from this meeting". Use whenever the user brings a
  problem statement, transcripts, documents or notes and wants work scoped so it can be
  split across parallel agents or teams, even if they do not say "epic".
---

# Epic Composer

<!--
  The skill itself. OpenCode reads it here; Claude Code loads it through the
  generated .claude/skills/<name>/SKILL.md pointer.
  contract: templates/_shared/doctrine/skill-execution.md
  version: 6.3.0, owner: John D
  invokes: .agents/skills/epic-interview/SKILL.md,
           .agents/skills/epic-acceptance-linter/SKILL.md,
           .agents/templates/epic/epic-shell.md,
           .agents/scripts/plan.py,
           .agents/scripts/tracker.py,
           .agents/evals/epic-rubric.md
  doctrine: .agents/doctrine/source-discipline.md,
            .agents/doctrine/acceptance-criteria-rules.md,
            .agents/doctrine/context-discovery.md,
            .agents/doctrine/agent-plan-schema.md,
            .agents/doctrine/parallelization-doctrine.md
-->

Shape one Epic from named source material into an issue body that people can
review and agents can execute. The prose says why and what; the `agent-plan`
block says which stories exist, what each owns, what it depends on and how it
proves itself — that block is what `story-decomposer` and `wave-dispatcher`
read, so it has to be right, not just plausible.

## Inputs

- Required: the source paths, transcript, note, or problem statement named by the
  caller.
- Read: `.agents/templates/epic/epic-shell.md`, `agent-plan-schema.md`, and the
  other doctrine files above.
- In a codebase: the top-level layout (`git ls-files | head -200` or the
  directories the sources name) so `owns` paths are real, not guessed.
- Optional: the existing Epic issue (`tracker.py get <ref>`) when refining.
- Do not read: unrelated repositories, whole directory trees, or generated
  harness output.

## Deterministic Steps

1. **Inventory the sources.** List each input path once; do not summarize yet.
2. **Extract facts.** For each source, record only: problem, actors, desired
   outcome, constraints, prior decisions, and unknowns. Label each as stated,
   inferred, or unknown per `source-discipline.md`.
3. **Discover context** per `context-discovery.md`: greenfield or brownfield,
   the modules the work touches, and the test/verify commands the repo uses
   (from its `AGENTS.md`, `Makefile`, `package.json`, `pyproject.toml`).
4. **Draft the outcome and scope.** Use the exact headings in `epic-shell.md`.
   Keep one outcome; list explicit exclusions.
5. **Draft 3–8 acceptance criteria.** Use the form `When …, then …, so that …`,
   labelled AC1…ACn. If the count exceeds 8, split the Epic instead.
6. **Slice the stories for parallel agents.** Each story is a vertical slice one
   agent could finish and verify alone. For each, decide in the plan block:
   `acs` (or `constraint`), `size`, `priority`, `owns`, `depends_on`, `verify`.
   - Make `owns` as narrow as the work allows: stories that can run together
     must own disjoint paths. Two stories that would both edit a file either
     share a contract story they both depend on, or are sequenced.
   - Add `depends_on` only for a real output dependency, and name what
     crosses it in `consumes` (the upstream paths or `path::Symbol` it reads).
     If you can't name anything, there is no edge: drop it so the stories run
     in parallel. Waves are computed from it — do not write wave numbers.
   - `verify` is the exact command this repo uses (step 3), scoped to the story.
7. **Name shared contracts.** When parallel stories share an interface, type,
   schema, or file format, add a `contracts` entry owned by one story and make
   the consumers depend on that story. Otherwise `contracts: []`.
8. **Gap gate.** If a gap changes scope, actors, ownership or acceptance, run
   `.agents/skills/epic-interview/SKILL.md` and ask only its blockers. If the criteria
   need review, run `.agents/skills/epic-acceptance-linter/SKILL.md`.
9. **Check.** Write the body to a file, then
   `python3 .agents/scripts/plan.py check "$epic"` — it validates the plan,
   writes the story table and map, checks the prose sections and prints the
   waves. Fix the plan on `FAIL` (overlapping `owns` between parallel stories
   means re-slice or add a dependency), never the checker.
10. **Quality pass.** When the caller asks for a strict review, or the Epic is
    about to be decomposed, apply `.agents/evals/epic-rubric.md` and append its
    report. It advises; it never blocks the output.
11. **Publish when asked.** `tracker.py create --title "Epic: <outcome>"
    --body-file "$epic" --label factory:drafted`, then set `epic:` in the block
    to the returned number and `tracker.py put` the re-synced body. Without a
    request, return the body. Every Epic you draft keeps the shell's
    `factory:drafted` marker and label: the factory starts it only once a
    person adds `factory:approved`. Never remove either, and never add an
    approval label (`tracker.py` refuses it).

## LLM Judgment

Use judgment only for:

- synthesizing the problem and outcome from conflicting source material;
- choosing the smallest coherent vertical slices and their ownership boundaries;
- sizing and dependency calls when the sources are ambiguous;
- deciding whether a gap is a blocker or a deferrable.

Do not invent facts, metrics, approvals, acceptance criteria, or paths. Mark
inferred content and unknowns; a path you could not confirm gets `(new)` in the
prose and a note in Risks.

## Output

One Epic issue body from `epic-shell.md`, titled `Epic: <outcome>`, containing:

- the prose sections;
- the generated story table and parallelization map (from `plan.py check`);
- exactly one `agent-plan` block that passes `plan.py validate`.

Then the waves `plan.py check` printed, so the caller sees what can start
immediately. When step 10 ran, add the rubric report after the body.

## Stop Conditions

- Stop and ask if the source has no identifiable problem or outcome.
- Stop and ask if two sources contradict each other on scope or acceptance.
- Stop and split if the work has two unrelated outcomes or more than 8 ACs.
- Stop if `plan.py check` still fails after one re-slice; report the conflict.
- Do not write story bodies or tasks; that is `story-decomposer` and
  `task-decomposer`.

## Token Budget

- Default: read the named sources, `epic-shell.md`, the doctrine files, and the
  repo layout needed for real `owns` paths.
- Do not enumerate the repository beyond the modules the work touches.
- Target ≤ 1,200 words of prose. If it is longer, split the Epic or state why;
  the plan block and generated tables do not count toward it.
- Reuse the template headings; do not restate the plan in prose.
