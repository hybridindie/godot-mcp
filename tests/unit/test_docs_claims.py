"""Pin documentation claims that are not covered by the registry count test.

The docs are part of the product surface. These guards catch the drift that a
human reader notices but the test suite otherwise misses: dead tutorial links,
the wrong CLI name, and branding that silently reverts to the repo slug.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastmcp import Client

from mcp_server import CONTRACT_VERSION, MIN_COMPATIBLE_CONTRACT
from mcp_server.server import create_server

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE = REPO_ROOT / "docs" / "site"


def _docs_sources() -> list[Path]:
    files = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "AGENTS.md",
        REPO_ROOT / "CONTRIBUTING.md",
    ]
    for pattern in ("docs/**/*.md", "docs/site/**/*.mjs", "mcp_server/**/*.py"):
        files.extend(REPO_ROOT.glob(pattern))
    return [
        path
        for path in files
        if path.is_file()
        and "node_modules" not in path.parts
        and "dist" not in path.parts
        and path.name != "changelog.md"
    ]


def test_docs_do_not_link_the_missing_top_level_tutorial() -> None:
    """The tutorial lives at ``docs/tutorial.md``; ``TUTORIAL.md`` 404s."""
    stale = [
        str(path.relative_to(REPO_ROOT))
        for path in _docs_sources()
        if "TUTORIAL.md" in path.read_text(encoding="utf-8")
    ]
    assert not stale, "docs point at the nonexistent TUTORIAL.md:\n" + "\n".join(stale)


def test_docs_use_the_published_cli_name() -> None:
    """The console script is ``godot-editor-mcp``; ``uv run godot-mcp`` fails."""
    stale = [
        str(path.relative_to(REPO_ROOT))
        for path in _docs_sources()
        if "uv run godot-mcp" in path.read_text(encoding="utf-8")
    ]
    assert not stale, "docs use the wrong CLI name:\n" + "\n".join(stale)


def test_product_name_is_godot_editor_mcp() -> None:
    """The human-facing product is **Godot Editor MCP**, not the repo slug."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert re.search(r"<h1[^>]*>Godot Editor MCP</h1>", readme)

    config = (SITE / ".vitepress" / "config.mts").read_text(encoding="utf-8")
    assert "title: 'Godot Editor MCP'" in config
    assert "siteTitle: 'Godot Editor MCP'" in config

    home = (SITE / "index.md").read_text(encoding="utf-8")
    assert "name: 'Godot Editor MCP'" in home

    llms_gen = (SITE / "llms-gen.mjs").read_text(encoding="utf-8")
    assert "const TITLE = 'Godot Editor MCP'" in llms_gen


def test_creator_and_developer_tracks_exist_and_are_linked() -> None:
    config = (SITE / ".vitepress" / "config.mts").read_text(encoding="utf-8")
    home = (SITE / "index.md").read_text(encoding="utf-8")

    for page in ("for-creators.md", "for-developers.md"):
        assert (SITE / page).is_file(), f"missing audience landing page: {page}"
        slug = page.removesuffix(".md")
        assert f"link: '/{slug}'" in config, f"{slug} is not in the sidebar/nav"
        assert f"./{slug}" in home, f"home page does not link to {slug}"


def test_no_stale_calver_typo_in_architecture_docs() -> None:
    architecture = (SITE / "architecture" / "index.md").read_text(encoding="utf-8")
    assert "Cadver" not in architecture


def test_prompt_and_resource_counts_match_the_registry() -> None:
    """The readable reference states the prompt/resource totals; pin them."""
    text = (SITE / "reference-prompts.md").read_text(encoding="utf-8")
    prompt_claim = re.search(r"## Workflow prompts \((\d+)\)", text)
    resource_claim = re.search(
        r"## Read-only resources \((\d+) resources \+ (\d+) depth template\)", text
    )
    assert prompt_claim and resource_claim, "reference-prompts.md totals not found"

    async def _counts() -> tuple[int, int, int]:
        async with Client(create_server()) as client:
            prompts = len(await client.list_prompts())
            resources = len(await client.list_resources())
            templates = len(await client.list_resource_templates())
            return prompts, resources, templates

    prompts, resources, templates = asyncio.run(_counts())
    assert int(prompt_claim.group(1)) == prompts
    assert int(resource_claim.group(1)) == resources
    assert int(resource_claim.group(2)) == templates


def test_examples_claim_matches_the_survivors_project() -> None:
    """``guides-examples.md`` states the GUT test/file totals of the example."""
    text = (SITE / "guides-examples.md").read_text(encoding="utf-8")
    claim = re.search(r"(\d+) GUT tests across (\d+) files", text)
    assert claim, "guides-examples.md GUT test claim not found"

    files = list((REPO_ROOT / "examples" / "survivors" / "tests").rglob("test_*.gd"))
    tests = sum(
        len(re.findall(r"^func test_", path.read_text(encoding="utf-8"), re.M))
        for path in files
    )
    assert int(claim.group(1)) == tests
    assert int(claim.group(2)) == len(files)


def test_contract_page_is_linked_and_pins_the_live_values() -> None:
    """The dedicated contract page must exist, be discoverable, and not drift."""
    page = (SITE / "reference-contract.md").read_text(encoding="utf-8")
    assert f"contract_version = {CONTRACT_VERSION}" in page
    assert f"min_compatible_contract = {MIN_COMPATIBLE_CONTRACT}" in page

    for source, needle in {
        "reference.md": "reference-contract.md",
        "concepts.md": "reference-contract.md",
        "for-developers.md": "reference-contract.md",
        "reference-consumers.md": "reference-contract.md",
        ".vitepress/config.mts": "/reference-contract",
        "llms-gen.mjs": "reference-contract.md",
    }.items():
        text = (SITE / source).read_text(encoding="utf-8")
        assert needle in text, f"{source} does not link the contract page"

    for heading in (
        "What the contract covers",
        "What the contract does not cover",
        "Why it has its own version",
        "How negotiation works",
        "What bumps the contract",
    ):
        assert heading in page, f"contract page is missing: {heading}"


def test_canonical_contract_wording_is_not_reversed() -> None:
    """Below the floor means the client is too old, not too new."""
    contracts = (REPO_ROOT / "docs" / "tool-contracts.md").read_text(encoding="utf-8")
    assert "Below the floor, the client is too **old**" in contracts
    assert "Below the floor, the client is too new" not in contracts


def test_agents_has_one_canonical_wiki_fabric_block() -> None:
    """AGENTS.md is shared by every harness; keep one wiki-fabric block."""
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert text.count("## wiki-fabric") == 1
    assert "## wiki-fabric (opencode)" not in text
    assert text.count("This project is connected to a knowledge fabric") == 1
