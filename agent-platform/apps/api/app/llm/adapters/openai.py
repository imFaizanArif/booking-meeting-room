"""OpenAI Chat Completions adapter (also serves any OpenAI-compatible server via base_url).

Not expressible: Anthropic-style signed reasoning replay (ignored), JSON Schema keywords
OpenAI's strict mode rejects (we send `strict: false`, so the schema is a strong hint and
the orchestrator validates the result).
"""

from __future__ import annotations

import json
from typing import Any

from app.llm import errors
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

_FINISH = {
    "stop": StopReason.end_turn,
    "tool_calls": StopReason.tool_use,
    "function_call": StopReason.tool_use,
    "length": StopReason.max_tokens,
    "content_filter": StopReason.content_filter,
}


def to_openai_messages(req: LLMRequest) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in req.messages:
        if isinstance(msg, SystemMessage):
            out.append({"role": "system", "content": msg.content})
        elif isinstance(msg, UserMessage):
            out.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AssistantMessage):
            item: dict[str, Any] = {"role": "assistant", "content": msg.content}
            if msg.tool_calls:
                item["tool_calls"] = [
                    {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                    for c in msg.tool_calls
                ]
            out.append(item)
        elif isinstance(msg, ToolResultMessage):
            out.append({"role": "tool", "tool_call_id": msg.tool_call_id, "content": msg.content})
    return out


def to_openai_tools(req: LLMRequest) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {"name": t.name, "description": t.description[:1024], "parameters": t.input_schema},
        }
        for t in req.tools
    ]


def parse_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"__invalid_json__": raw}
    return value if isinstance(value, dict) else {"value": value}


class OpenAIAdapter(HttpAdapter):
    provider_name = "openai"
    default_base_url = "https://api.openai.com/v1"

    def headers(self) -> dict[str, str]:
        headers = super().headers()
        if self.config.api_key:
            headers["authorization"] = f"Bearer {self.config.api_key}"
        org = self.config.metadata.get("organization")
        if org:
            headers["openai-organization"] = str(org)
        return headers

    def build_payload(self, req: LLMRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": req.model, "messages": to_openai_messages(req)}
        if req.tools:
            payload["tools"] = to_openai_tools(req)
            payload["tool_choice"] = req.tool_choice.value
        if req.temperature is not None:
            payload["temperature"] = req.temperature
        if req.max_tokens is not None:
            payload["max_completion_tokens"] = req.max_tokens
        if req.response_format is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": req.response_format.name,
                    "schema": req.response_format.json_schema,
                    "strict": False,
                },
            }
        payload.update(req.extras.get("openai") or {})
        return payload

    async def generate(self, req: LLMRequest) -> LLMResponse:
        body, latency_ms = await self.post_json("/chat/completions", self.build_payload(req))
        return self.parse_response(body, latency_ms, req.model)

    @staticmethod
    def parse_response(body: dict[str, Any], latency_ms: int, requested_model: str) -> LLMResponse:
        choices = body.get("choices") or []
        if not choices:
            raise errors.ProviderUnavailable("OpenAI returned no choices", details={"provider": "openai"})
        choice = choices[0]
        message = choice.get("message") or {}
        calls = [
            ToolCallRequest(
                id=c.get("id") or f"call_{i}",
                name=c["function"]["name"],
                arguments=parse_arguments(c["function"].get("arguments")),
            )
            for i, c in enumerate(message.get("tool_calls") or [])
        ]
        usage = body.get("usage") or {}
        return LLMResponse(
            message=AssistantMessage(content=message.get("content"), tool_calls=calls),
            stop_reason=_FINISH.get(choice.get("finish_reason") or "", StopReason.other),
            usage=Usage(input_tokens=usage.get("prompt_tokens", 0), output_tokens=usage.get("completion_tokens", 0)),
            model=body.get("model") or requested_model,
            latency_ms=latency_ms,
        )

    async def health(self, model: str | None = None) -> str:
        import httpx

        try:
            async with self.client() as client:
                response = await client.get("/models")
        except httpx.TransportError as exc:
            raise errors.ProviderUnavailable("Provider is unreachable", details={"provider": "openai"}) from exc
        if response.status_code >= 400:
            raise self.classify(response)
        count = len((response.json() or {}).get("data") or [])
        return f"Connected. {count} models visible"
