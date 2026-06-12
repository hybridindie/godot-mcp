#!/usr/bin/env python3
"""Cloud LLM client for godot-mcp evals.

Supports Anthropic Claude, OpenAI GPT, and Google Gemini via their respective
REST APIs. Designed to be a drop-in alternative to OllamaAgent for cross-model
comparison matrices.

Usage:
    from evals.cloud_client import CloudAgent

    agent = CloudAgent(bridge, provider="anthropic", model="claude-sonnet-4")
    agent = CloudAgent(bridge, provider="openai", model="gpt-4o")
    agent = CloudAgent(bridge, provider="google", model="gemini-2.5-pro")
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from evals.correction import format_correction
from evals.history import COMPRESSION_THRESHOLD, char_len, compress_history


@dataclass
class CloudCall:
    """Raw response from a cloud LLM API."""

    tool: str
    params: dict[str, Any]
    reasoning: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0


def _anthropic_call(
    system: str,
    messages: list[dict],
    model: str,
    api_key: str | None = None,
    timeout: float = 120.0,
) -> CloudCall:
    """Call Anthropic Messages API."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    # Convert message history to Anthropic format
    anthropic_messages: list[dict] = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "assistant"
        anthropic_messages.append({"role": role, "content": msg["content"]})

    payload = {
        "model": model,
        "max_tokens": 1024,
        "system": system,
        "messages": anthropic_messages,
        "temperature": 0.2,
    }

    t0 = time.perf_counter()
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    data = resp.json()

    content = data["content"][0]["text"]
    parsed = _extract_json(content)

    usage = data.get("usage", {})
    return CloudCall(
        tool=parsed.get("tool", "done"),
        params=parsed.get("params", {}),
        reasoning=parsed.get("reasoning", ""),
        prompt_tokens=usage.get("input_tokens", 0),
        completion_tokens=usage.get("output_tokens", 0),
        provider="anthropic",
        model=model,
        latency_ms=latency_ms,
    )


def _openai_call(
    system: str,
    messages: list[dict],
    model: str,
    api_key: str | None = None,
    timeout: float = 120.0,
) -> CloudCall:
    """Call OpenAI Chat Completions API."""
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")

    headers = {
        "Authorization": f"Bearer {key}",
        "content-type": "application/json",
    }

    all_messages = [{"role": "system", "content": system}, *messages]

    payload = {
        "model": model,
        "messages": all_messages,
        "max_tokens": 1024,
        "temperature": 0.2,
    }

    t0 = time.perf_counter()
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    data = resp.json()

    content = data["choices"][0]["message"]["content"]
    parsed = _extract_json(content)

    usage = data.get("usage", {})
    return CloudCall(
        tool=parsed.get("tool", "done"),
        params=parsed.get("params", {}),
        reasoning=parsed.get("reasoning", ""),
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        provider="openai",
        model=model,
        latency_ms=latency_ms,
    )


def _google_call(
    system: str,
    messages: list[dict],
    model: str,
    api_key: str | None = None,
    timeout: float = 120.0,
) -> CloudCall:
    """Call Google Gemini API."""
    key = api_key or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_API_KEY not set")

    # Gemini uses a different message format (no system role)
    gemini_messages: list[dict] = []
    gemini_messages.append({"role": "user", "parts": [{"text": system}]})
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        gemini_messages.append({"role": role, "parts": [{"text": msg["content"]}]})

    payload = {
        "contents": gemini_messages,
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1024,
        },
    }

    t0 = time.perf_counter()
    resp = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    data = resp.json()

    content = data["candidates"][0]["content"]["parts"][0]["text"]
    parsed = _extract_json(content)

    usage = data.get("usageMetadata", {})
    return CloudCall(
        tool=parsed.get("tool", "done"),
        params=parsed.get("params", {}),
        reasoning=parsed.get("reasoning", ""),
        prompt_tokens=usage.get("promptTokenCount", 0),
        completion_tokens=usage.get("candidatesTokenCount", 0),
        provider="google",
        model=model,
        latency_ms=latency_ms,
    )


def _extract_json(content: str) -> dict:
    """Extract JSON tool call from LLM response text."""
    try:
        # Handle markdown-wrapped JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return json.loads(content)
    except (json.JSONDecodeError, IndexError):
        pass

    # Fallback: find the first JSON object
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(content[start:end + 1])
        except json.JSONDecodeError:
            pass

    return {"tool": "done", "params": {}, "reasoning": f"Parse error: {content[:80]}"}


class CloudAgent:
    """LLM agent that uses cloud APIs (Claude/GPT/Gemini) to choose tools."""

    PROVIDERS = {
        "anthropic": _anthropic_call,
        "openai": _openai_call,
        "google": _google_call,
    }

    DEFAULT_MODELS = {
        "anthropic": "claude-sonnet-4-20250514",
        "openai": "gpt-4o-2024-08-06",
        "google": "gemini-2.5-pro-preview-06-05",
    }

    def __init__(
        self,
        bridge,
        provider: str = "anthropic",
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        if provider not in self.PROVIDERS:
            raise ValueError(
                f"Unknown provider '{provider}'. "
                f"Supported: {', '.join(self.PROVIDERS.keys())}"
            )
        self._bridge = bridge
        self._provider = provider
        self._model = model or self.DEFAULT_MODELS[provider]
        self._api_key = api_key
        self._history: list[dict] = []
        # Track the most recent call so a failure can be quoted back as a
        # correction in the next user message (issue #149).
        self._last_tool: str = ""
        self._last_params: dict[str, Any] = {}
        # History compression (issue #148): keep raw history, send a summarized
        # view past the threshold. _last_compression lets the runner record it.
        self._compression_threshold: int = COMPRESSION_THRESHOLD
        self._last_compression: dict[str, int] | None = None

    def _history_view(self) -> list[dict]:
        """Return the history to send: compressed past the step threshold.

        Compression is judged by character count, not message count — a shorter
        message list can still be larger in chars. Only send (and record) the
        compressed view when it actually shrinks the prompt.
        """
        view = compress_history(self._history, self._compression_threshold)
        if view is not self._history:
            before, after = char_len(self._history), char_len(view)
            if after < before:
                self._last_compression = {"before_chars": before, "after_chars": after}
                return view
        self._last_compression = None
        return self._history

    def _system_prompt(self, task: str, available_tools: list[dict]) -> str:
        """Build the system prompt with structured tool descriptions."""
        lines: list[str] = []
        for t in available_tools:
            lines.append(f"- {t['name']}: {t.get('description', 'No description')}")
            params = t.get("parameters", {})
            if params:
                lines.append("  Parameters:")
                for pname, pspec in params.items():
                    req = " (required)" if pspec.get("required") else ""
                    default = f" [default: {pspec.get('default')}]" if "default" in pspec else ""
                    lines.append(f"    - {pname}: {pspec.get('type', 'any')}{req}{default}")
                    if "description" in pspec:
                        lines.append(f"      {pspec['description']}")
        tools_desc = "\n".join(lines)

        return (
            f"You are an AI agent controlling a Godot game engine via MCP tools.\n\n"
            f"TASK: {task}\n\n"
            f"AVAILABLE TOOLS:\n{tools_desc}\n\n"
            f"RULES:\n"
            f"1. Only call tools that are listed above.\n"
            f"2. If a tool fails, read the error hint and choose a recovery action.\n"
            f"3. Respond ONLY with a JSON object:\n"
            f'   {{"tool": "...", "params": {{...}}, "reasoning": "..."}}\n'
            f"4. Use empty params {{}} if the tool takes no arguments.\n"
            f"5. You MUST take at least one action to make progress on the task.\n"
            f"6. Only return {{\"tool\": \"done\"}} AFTER you have completed the task.\n"
            f"7. Do NOT take extra actions once the task is complete. Call done immediately.\n"
            f"8. If the TASK gives explicit steps, follow them exactly and do NOT deviate."
        )

    def _ask(self, task: str, available_tools: list[dict]) -> CloudCall:
        """Ask the cloud LLM to choose the next tool."""
        system = self._system_prompt(task, available_tools)
        call_fn = self.PROVIDERS[self._provider]

        cloud_call = call_fn(
            system=system,
            messages=self._history_view(),
            model=self._model,
            api_key=self._api_key,
        )

        self._history.append({"role": "assistant", "content": json.dumps({
            "tool": cloud_call.tool,
            "params": cloud_call.params,
            "reasoning": cloud_call.reasoning,
        })})
        self._last_tool = cloud_call.tool
        self._last_params = cloud_call.params
        return cloud_call

    async def _execute(self, call: CloudCall) -> dict:
        """Execute a tool call via the bridge (async)."""
        if call.tool == "done":
            return {"ok": True, "result": {}, "done": True}

        cmd = f"cmd_{call.tool}"
        try:
            t0 = time.perf_counter()
            response = await self._bridge.send(cmd, call.params)
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            return {
                "ok": response.ok,
                "result": response.result or {},
                "error": response.error,
                "hint": response.hint,
                "done": False,
                "latency_ms": latency_ms,
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "hint": "Bridge execution failed", "done": False}

    def _add_result(self, result: dict) -> None:
        """Add the tool result to history for the LLM.

        On failure, append a dynamic correction (issue #149) that quotes the
        failed call and its hint, so the model adapts instead of repeating it.
        """
        summary = json.dumps({
            "ok": result["ok"],
            "error": result.get("error"),
            "hint": result.get("hint"),
            "result_keys": list(result.get("result", {}).keys()),
        })
        content = f"Tool result: {summary}"
        if not result.get("ok", True):
            content += "\n" + format_correction(
                self._last_tool, self._last_params, result.get("error"), result.get("hint")
            )
        self._history.append({"role": "user", "content": content})

    async def run_task(
        self,
        task: str,
        available_tools: list[dict],
        max_steps: int = 10,
    ) -> list[dict]:
        """Run a task with the cloud LLM agent, returning the step-by-step trace."""
        steps: list[dict] = []
        for i in range(max_steps):
            call = self._ask(task, available_tools)
            result = await self._execute(call)
            self._add_result(result)
            steps.append({
                "step": i + 1,
                "tool": call.tool,
                "params": call.params,
                "reasoning": call.reasoning,
                "ok": result["ok"],
                "error": result.get("error"),
                "hint": result.get("hint"),
                "latency_ms": result.get("latency_ms"),
                "llm_latency_ms": call.latency_ms,
                "tokens": call.prompt_tokens + call.completion_tokens,
            })
            if result.get("done") or call.tool == "done":
                break
        return steps
