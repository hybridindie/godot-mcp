<!--
Before opening:
- A tracking issue exists (`closes #N` in the title/body)
- The test was red before the fix (tests first per .opencode/rules/testing.md)
- Preflight is green: pytest / ruff / mypy / zero-skip

Docs: https://hybridindie.github.io/godot-mcp/ (for LLM agents: /llms.txt, /llms-full.txt)
-->

## Summary

<!-- What changed and why -->

## Issue

Closes #

## Test plan

- [ ] `uv run pytest -q`
- [ ] `uv run ruff check .`
- [ ] `uv run mypy`
- [ ] `./.opencode/hooks/check-no-skipped-tests.sh`
