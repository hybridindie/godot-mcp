---
read_when: "Adding, upgrading, or auditing a dependency"
---

# Dependencies: Locked, Audited, Justified

## MUST

- Commit the lockfile (`uv.lock`, `package-lock.json`, `Cargo.lock`, …) and
  install from it in CI (`uv sync --locked`, `npm ci`).
- Use the project's package manager to change dependencies (`uv add`, not
  `pip install`).
- Declare floors with an upper bound where the ecosystem supports it; the
  lockfile pins exact versions. Never lower a security floor.
- A high or critical advisory with a fixed version (Dependabot,
  `.github/dependabot.yml`) is fixed before the next release; an accepted
  exception is documented with a reason and a review date.
- A new dependency is justified in the PR: what it does, licence, maintenance
  signal, why not the standard library or an existing dependency.

## SHOULD

- Batch routine updates; review major upgrades individually with release notes.
- Remove unused dependencies and extras.

## ANTI-PATTERNS

- `--force` / `--no-deps` to get past a conflict.
- A git ref or unpinned URL in a release path.
- A dependency for a ten-line function.
