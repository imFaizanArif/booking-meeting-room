"""Ollama /api/chat adapter.

Ollama does not return tool call ids, so stable ids are synthesised from the position.
Structured output uses Ollama's `format` (a JSON Schema).
"""

from __future__ import annotations

from typing import Any

import httpx

from app.llm import errors
from app.llm.adapters.openai import parse_arguments, to_openai_tools
from app.llm.base import HttpAdapter
from app.llm.types import (
    AssistantMessage,
    LLMRequest,
    LLMResponse,
    StopReason,
    SystemMessage,
    ToolCallRequest,
    ToolResultMessage,
    Usage,
    UserMessage,
)


def to_ollama_messages(req: LLMRequest) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in req.messages:
        if isinstance(msg, SystemMessage):
            out.append({"role": "system", "content": msg.content})
        elif isinstance(msg, UserMessage):
            out.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AssistantMessage):
            item: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                item["tool_calls"] = [{"function": {"name": c.name, "arguments": c.arguments}} for c in msg.tool_calls]
            out.append(item)
        elif isinstance(msg, ToolResultMessage):
            out.append({"role": "tool", "content": msg.content, "tool_name": msg.name})
    return out


class OllamaAdapter(HttpAdapter):
    provider_name = "ollama"
    default_base_url = "http://localhost:11434"

    def build_payload(self, req: LLMRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": req.model, "messages": to_ollama_messages(req), "stream": False}
        if req.tools:
            payload["tools"] = to_openai_tools(req)
        options: dict[str, Any] = {}
        if req.temperature is not None:
            options["temperature"] = req.temperature
        if req.max_tokens is not None:
            options["num_predict"] = req.max_tokens
        if options:
            payload["options"] = options
        if req.response_format is not None:
            payload["format"] = req.response_format.json_schema
        payload.update(req.extras.get("ollama") or {})
        return payload

    async def generate(self, req: LLMRequest) -> LLMResponse:
        body, latency_ms = await self.post_json("/api/chat", self.build_payload(req))
        message = body.get("message") or {}
        calls = [
            ToolCallRequest(
                id=f"call_{i}", name=c["function"]["name"], arguments=parse_arguments(c["function"].get("arguments"))
            )
            for i, c in enumerate(message.get("tool_calls") or [])
        ]
        done = body.get("done_reason")
        stop = StopReason.tool_use if calls else (StopReason.max_tokens if done == "length" else StopReason.end_turn)
        return LLMResponse(
            message=AssistantMessage(content=message.get("content") or None, tool_calls=calls),
            stop_reason=stop,
            usage=Usage(input_tokens=body.get("prompt_eval_count", 0), output_tokens=body.get("eval_count", 0)),
            model=body.get("model") or req.model,
            latency_ms=latency_ms,
        )

    async def health(self, model: str | None = None) -> str:
        try:
            async with self.client() as client:
                response = await client.get("/api/tags")
        except httpx.TransportError as exc:
            raise errors.ProviderUnavailable("Ollama is unreachable", details={"provider": "ollama"}) from exc
        if response.status_code >= 400:
            raise self.classify(response)
        names = [m.get("name") for m in (response.json() or {}).get("models", [])]
        return f"Connected. {len(names)} local models" + (f", e.g. {names[0]}" if names else "")
