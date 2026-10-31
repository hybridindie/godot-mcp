---
read_when: "Changing CI workflows, build steps, caching, or release automation"
---

# CI/CD: One Command, Same Result Everywhere

If a gate can't be reproduced locally, it isn't a gate.

## MUST

- Every blocking gate is runnable locally, and `/preflight` runs the same
  checks.
- The blocking job fails on lint, type errors, failing tests, unconditional
  skips, secret leaks, and invalid config.
- Pin tool and action versions; update them deliberately.
- Install from the lockfile; no network-dependent tests in the blocking job.
- Gates run on every PR, not only on `main`.
- Secrets are never echoed to logs or exposed to fork PRs.

## SHOULD

- Keep the blocking job fast (target < 10 min); put slow suites (integration,
  evals, headless engine runs) in a separate job or nightly.
- Cache keyed on the lockfile; build an artifact once and reuse it.
- Cancel superseded runs with concurrency groups.
- Upload logs/screenshots/coverage on failure.
- Release workflows reuse the CI workflow as their gate.
