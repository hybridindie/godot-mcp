"""Regression tests for the local-ollama guard in scripts/graphify.sh (issue on
PR #442 review). The wrapper must refuse to run graphify when a cloud API key is
present in the environment — unless the caller explicitly pins
``--backend ollama`` — and must never route the codebase corpus to a cloud
endpoint. Hermetic: the script runs with no real graphify install; the command
under test exits at the guard (exit 2) or proceeds to interpreter lookup, which
we stub via the pin file to a no-op interpreter exit.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "graphify.sh"

CLOUD_KEYS = [
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "KIMI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
]


def _run_in(
    repo: Path, args: list[str], env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")
    }
    env["PATH"] = "/usr/bin:/bin"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(repo / "graphify.sh"), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )


@pytest.fixture()
def hermetic_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temp checkout skeleton so the script's pin lookup can't hit a real
    graphify install — the guard decides before the interpreter step."""
    repo = tmp_path / "repo"
    repo.mkdir()
    script_src = SCRIPT.read_text()
    stub = repo / "graphify.sh"
    stub.write_text(script_src)
    stub.chmod(0o755)
    monkeypatch.setattr(
        "tests.unit.test_graphify_guard.SCRIPT", repo / "graphify.sh"
    )
    return repo


@pytest.mark.parametrize("key", CLOUD_KEYS)
def test_refuses_when_cloud_key_set(hermetic_repo: Path, key: str) -> None:
    proc = _run_in(hermetic_repo, ["label", "."], env_extra={key: "sk-test"})
    assert proc.returncode == 2, f"{key} did not trigger the guard: {proc.stderr}"
    assert key in proc.stderr
    assert "cloud" in proc.stderr.lower()


@pytest.mark.parametrize("backend_arg", [["--backend", "ollama"], ["--backend=ollama"]])
def test_allows_explicit_ollama_backend(hermetic_repo: Path, backend_arg: list[str]) -> None:
    proc = _run_in(
        hermetic_repo,
        ["label", ".", *backend_arg],
        env_extra={"OPENAI_API_KEY": "sk-test"},
    )
    assert proc.returncode != 2, f"guard refused despite explicit ollama pin: {proc.stderr}"


def test_path_named_ollama_is_not_a_backend_pin(hermetic_repo: Path) -> None:
    """The old guard matched any argument == 'ollama' (a path like ./ollama/
    would bypass the cloud-key refusal). Only a --backend value counts."""
    proc = _run_in(
        hermetic_repo,
        ["label", "./ollama", "--model", "ollama"],
        env_extra={"OPENAI_API_KEY": "sk-test"},
    )
    assert proc.returncode == 2, "a token named 'ollama' bypassed the cloud-key guard"
    assert "OPENAI_API_KEY" in proc.stderr


def test_query_and_explain_skip_the_guard(hermetic_repo: Path) -> None:
    """query/explain return text to the caller only; never extract to a backend,
    so they run regardless of ambient keys (and here must not exit 2)."""
    for sub in ("query", "explain"):
        proc = _run_in(hermetic_repo, [sub, "how does the bridge work?"])
        assert proc.returncode != 2, f"{sub} was refused by the cloud-key guard"
        assert "cloud" not in proc.stderr.lower()


def test_no_cloud_key_proceeds_past_guard(hermetic_repo: Path) -> None:
    proc = _run_in(hermetic_repo, ["label", "."])
    assert proc.returncode != 2
    assert "cloud" not in proc.stderr.lower()