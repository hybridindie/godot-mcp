<!--
  ai-readable-spec-rules.md — Shared rules for AI-readable writing
  Referenced by: story-decomposer, task-decomposer
  version: 1.1.1, owner: John D
  Single source of truth for the "name specifics, state exists-vs-new, no
  pronouns, executable specs" rules previously restated in both decomposers.
-->

# AI-Readable Spec Rules

Stories and tasks are read by AI coding agents, not just humans. Write them to
be unambiguous enough that an agent can execute without asking "what file?",
"where does this go?", or "which component?".

## The rules

- **Name the specific components, modules, or systems** the work touches when
  known from the Epic or brownfield context.
- **Name the specific file path** when known. Example:
  `Add toPdf() method to src/services/ExportService.ts` not "add PDF method to
  export service."
- **Name the specific API endpoint or interface** when known. Example:
  `Add POST /api/reports/{id}/export endpoint in src/api/routes/reports.ts`.
- **Name the specific data model or schema** when known. Example:
  `Add pdf_export_job table migration in src/db/migrations/`.
- **State what exists vs. what is new.** Example: "Extend the existing
  ExportService class with a new toPdf() method" not "add PDF export." Mark
  new files as "(new)".
- **Include the test file path** when known. Example: "Add tests in
  src/services/__tests__/export-service.test.ts covering happy path and
  timeout."
- **Avoid pronouns and ambiguous references.** "The system" is vague. Name the
  component: "the export service," "the report API."
- **Make acceptance criteria executable specifications.** A test should be able
  to verify each Given/When/Then without human interpretation.
- **Link to relevant Epic sections.** Example: "See Epic NFR: performance
  < 200ms p95" or "See Epic constraint: must use existing auth middleware."
- **One task = one PR-sized unit.** If a task would produce more than ~100
  lines of code or touch more than 3 files, split it. (Task-level rule only;
  stories use the S/M/L sizing instead.)

## How callers use this file

- `story-decomposer` references this for the AI-readable writing of stories.
- `task-decomposer` references this for task-level writing (and applies the
  one-task-one-PR rule).
- The optional quality passes reuse these rules without restating them.