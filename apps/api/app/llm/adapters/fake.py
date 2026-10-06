"""Deterministic FakeLLMProvider for tests and offline demos.

Behaviour is data, read from `extras.fake`:

    {"script": [step, step, ...]}

The step index is the number of assistant turns already in the request (so step 0 answers
the first call, step 1 the call after the first tool result, ...); past the end the last
step repeats. A step is a sandboxed Jinja template that renders to JSON:

    {"content": "..."}                               plain answer
    {"tool_calls": [{"name": "...", "arguments": {}}]}  propose tool calls
    {"json": {...}}                                   structured output (serialised as content)

Template context: `input` (JSON parsed from the last user message when possible, else its
text), `tool_results` (parsed contents of tool results, oldest first), `last_tool_result`,
`iteration`, `tools` (names offered). Without a script the fake answers with a short echo,
or with a schema-shaped default object when structured output is requested.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from app.llm import errors
from app.llm.base import ProviderConfig
from app.llm.types import (
    AssistantMessage,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    StopReason,
    ToolCallRequest,
    ToolResultMessage,
    Usage,
    UserMessage,
)
from app.prompts.render import TemplateError, render


def _maybe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        return text


def default_for_schema(schema: dict[str, Any]) -> Any:
    kind = schema.get("type")
    if "default" in schema:
        return schema["default"]
    if "enum" in schema:
        return schema["enum"][0]
    if kind == "object":
        return {k: default_for_schema(v) for k, v in (schema.get("properties") or {}).items()
                if k in set(schema.get("required") or schema.get("properties") or [])}
    if kind == "array":
        return []
    if kind in ("integer", "number"):
        return 0
    if kind == "boolean":
        return False
    return ""


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class FakeLLMProvider:
    provider_name = "fake"

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config
        self.requests: list[LLMRequest] = []

    async def generate(self, req: LLMRequest) -> LLMResponse:
        self.requests.append(req)
        opts = req.extras.get("fake") or {}
        if opts.get("raise"):
            raise errors.ProviderUnavailable("Fake provider configured to fail", details={"provider": "fake"})
        script: list[Any] = opts.get("script") or []
        iteration = sum(1 for m in req.messages if isinstance(m, AssistantMessage))
        last_user = next((m.content for m in reversed(req.messages) if isinstance(m, UserMessage)), "")
        tool_results = [_maybe_json(m.content) for m in req.messages if isinstance(m, ToolResultMessage)]
        context = {
            "input": _maybe_json(last_user),
            "tool_results": tool_results,
            "last_tool_result": tool_results[-1] if tool_results else None,
            "iteration": iteration,
            "tools": [t.name for t in req.tools],
        }
        if script:
            step = script[min(iteration, len(script) - 1)]
            source = step if isinstance(step, str) else json.dumps(step)
            try:
                rendered = render(source, context)
                parsed = json.loads(rendered)
            except (TemplateError, json.JSONDecodeError) as exc:
                raise errors.InvalidRequest(f"Fake script step {iteration} is invalid: {exc}",
                                            details={"provider": "fake"}) from exc
            message = self._message_from_step(parsed, iteration)
        elif req.response_format is not None:
            message = AssistantMessage(content=json.dumps(default_for_schema(req.response_format.json_schema)))
        else:
            message = AssistantMessage(content=f"Acknowledged: {str(last_user)[:200]}")
        input_tokens = sum(_estimate_tokens(json.dumps(m.model_dump(), default=str)) for m in req.messages)
        output_tokens = _estimate_tokens(message.model_dump_json())
        return LLMResponse(
            message=message,
            stop_reason=StopReason.tool_use if message.tool_calls else StopReason.end_turn,
            usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
            model=req.model,
            latency_ms=1,
        )

    @staticmethod
    def _message_from_step(step: dict[str, Any], iteration: int) -> AssistantMessage:
        if "json" in step:
            return AssistantMessage(content=json.dumps(step["json"]))
        calls = [
            ToolCallRequest(id=f"fake_{iteration}_{i}", name=c["name"], arguments=c.get("arguments") or {})
            for i, c in enumerate(step.get("tool_calls") or [])
        ]
        return AssistantMessage(content=step.get("content"), tool_calls=calls)

    async def stream(self, req: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        response = await self.generate(req)
        if response.message.content:
            yield LLMStreamEvent(type="text_delta", text=response.message.content)
        for call in response.message.tool_calls:
            yield LLMStreamEvent(type="tool_call", tool_call=call)
        yield LLMStreamEvent(type="done", response=response)

    async def health(self, model: str | None = None) -> str:
        return "Fake provider is always available"
