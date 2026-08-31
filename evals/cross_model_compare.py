#!/usr/bin/env python3
"""Run cross-model comparison on a subset of tasks.

Usage:
    # Compare qwen3-coder:30b vs Claude on 5 representative tasks
    python -m evals.cross_model_compare \
        --providers ollama anthropic \
        --models qwen3-coder:30b claude-sonnet-4 \
        --tasks inspect_scene_tree script_write_and_read batch_set_property \
              physics_setup play_and_inspect

    # Full 28-task comparison (expensive for cloud models)
    python -m evals.cross_model_compare --providers ollama openai
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.llm_eval_v2 import (  # noqa: E402
    print_summary,
    run_llm_suite,
)


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Cross-model comparison for godot-mcp"
    )
    parser.add_argument(
        "--providers",
        nargs="+",
        default=["ollama"],
        help="LLM providers to test (e.g., ollama anthropic openai)",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=["qwen3-coder:30b"],
        help="Model names, one per provider",
    )
    parser.add_argument(
        "--tasks",
        nargs="+",
        default=None,
        help="Specific tasks (default: 5 representative tasks)",
    )
    parser.add_argument(
         "--max-steps",
        type=int,
        default=12,
        help="Max steps per task",
      )
    args = parser.parse_args()

    if len(args.providers) != len(args.models):
        print("❌ Error: --providers and --models must have the same count")
        sys.exit(1)

    default_tasks = [
        "inspect_scene_tree",
        "script_write_and_read",
        "batch_set_property",
        "physics_setup",
        "play_and_inspect",
    ]
    tasks = args.tasks or default_tasks

    all_results: dict[str, list] = {}

    for provider, model in zip(args.providers, args.models, strict=True):
        print(f"\n{'=' * 70}")
        print(f"  Running: {provider}:{model}")
        print(f"{'=' * 70}")

        results = await run_llm_suite(
            tasks=tasks,
            model=model,
            provider=provider,
            max_steps=args.max_steps,
          )
        all_results[f"{provider}:{model}"] = results
        print_summary(results)

      # Print comparison matrix
    print("\n" + "=" * 70)
    print("  Cross-Model Comparison Matrix")
    print("=" * 70)
    header = (
        f"  {'Provider:Model':<35} {'Mean':<8} "
        f"{'Comp%':<8} {'1stAtt%':<8} {'Steps':<8} {'Tokens':<10}"
    )
    print(header)
    print("  " + "-" * 68)
    for key, results in all_results.items():
        if not results:
            print(f"  {key:<35} NO RESULTS")
            continue
        mean_score = sum(r.score.overall for r in results) / len(results)
        compliance = sum(1 for r in results if r.score.overall >= 0.7) / len(results)
        first = sum(1 for r in results if r.first_attempt_correct) / len(results)
        steps = sum(r.step_count for r in results) / len(results)
        tokens = sum(r.token_usage.total_tokens for r in results) / len(results)
        print(
            f"  {key:<35} {mean_score:<8.2f} {compliance*100:<8.0f} "
            f"{first*100:<8.0f} {steps:<8.1f} {tokens:<10.0f}"
        )
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
