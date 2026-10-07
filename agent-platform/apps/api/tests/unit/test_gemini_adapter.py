"""Gemini adapter: message/tool translation, thought-signature replay, errors (httpx.MockTransport)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.llm import errors
from app.llm.adapters.gemini import GeminiAdapter, to_gemini_contents
from app.llm.base import ProviderConfig
from app.llm.types import (
    AssistantMessage,
    LLMRequest,
    ResponseFormat,
    StopReason,
    SystemMessage,
    ToolCallRequest,
    ToolChoice,
    ToolDefinition,
    ToolResultMessage,
    UserMessage,
)


def adapter(handler: Any) -> GeminiAdapter:
    return GeminiAdapter(
        ProviderConfig(provider_type="gemini", base_url=None, api_key="g-key-123456"),
        transport=httpx.MockTransport(handler),
    )


def test_translation_system_tools_and_merged_results() -> None:
    req = LLMRequest(
        model="gemini-2.5-flash",
        messages=[
            SystemMessage(content="be brief"),
            UserMessage(content="hi"),
            AssistantMessage(
                tool_calls=[
                    ToolCallRequest(id="a", name="t1", arguments={"x": 1}),
                    ToolCallRequest(id="b", name="t2", arguments={}),
                ]
            ),
            ToolResultMessage(tool_call_id="a", name="t1", content='{"ok": true}'),
            ToolResultMessage(tool_call_id="b", name="t2", content="plain text"),
        ],
    )
    system, contents = to_gemini_contents(req)
    assert system == {"parts": [{"text": "be brief"}]}
    assert [c["role"] for c in contents] == ["user", "model", "user"]
    responses = contents[2]["parts"]
    assert responses[0]["functionResponse"] == {"name": "t1", "response": {"ok": True}}
    assert responses[1]["functionResponse"] == {"name": "t2", "response": {"result": "plain text"}}


def test_thought_signature_replayed_with_edited_arguments() -> None:
    original = AssistantMessage(
        tool_calls=[ToolCallRequest(id="c", name="submit", arguments={"rate": 90})],
        provider_state={
            "provider": "gemini",
            "parts": [{"functionCall": {"name": "submit", "args": {"rate": 85}}, "thoughtSignature": "sig=="}],
        },
    )
    _, contents = to_gemini_contents(LLMRequest(model="m", messages=[UserMessage(content="go"), original]))
    part = contents[1]["parts"][0]
    assert part["thoughtSignature"] == "sig=="
    assert part["functionCall"]["args"] == {"rate": 90}


async def test_generate_parses_calls_usage_and_payload() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "role": "model",
                            "parts": [
                                {"text": "thinking", "thought": True},
                                {"functionCall": {"name": "search", "args": {"q": "python"}}, "thoughtSignature": "s1"},
                            ],
                        },
                    }
                ],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "thoughtsTokenCount": 2},
            },
        )

    req = LLMRequest(
        model="gemini-2.5-flash",
        messages=[UserMessage(content="find")],
        tools=[ToolDefinition(name="search", input_schema={"type": "object"})],
        tool_choice=ToolChoice.required,
        response_format=None,
        max_tokens=100,
    )
    res = await adapter(handler).generate(req)
    assert seen["url"].endswith("/models/gemini-2.5-flash:generateContent")
    assert seen["key"] == "g-key-123456"
    assert seen["body"]["toolConfig"]["functionCallingConfig"]["mode"] == "ANY"
    assert seen["body"]["tools"][0]["functionDeclarations"][0]["parametersJsonSchema"] == {"type": "object"}
    assert res.stop_reason == StopReason.tool_use
    assert res.message.tool_calls[0].arguments == {"q": "python"}
    assert res.usage.input_tokens == 10 and res.usage.output_tokens == 7
    assert res.message.provider_state and all(not p.get("thought") for p in res.message.provider_state["parts"])


def test_structured_output_payload() -> None:
    payload = adapter(lambda r: httpx.Response(200)).build_payload(
        LLMRequest(
            model="m",
            messages=[UserMessage(content="x")],
            response_format=ResponseFormat(json_schema={"type": "object"}),
        )
    )
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert payload["generationConfig"]["responseJsonSchema"] == {"type": "object"}


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (429, {"error": {"message": "quota"}}, errors.RateLimitedError),
        (403, {"error": {"message": "denied"}}, errors.AuthFailed),
        (400, {"error": {"message": "API key not valid"}}, errors.AuthFailed),
        (503, {"error": {"message": "overloaded"}}, errors.ProviderUnavailable),
        (400, {"error": {"message": "bad"}}, errors.InvalidRequest),
    ],
)
async def test_error_mapping(status: int, body: dict[str, Any], error: type[Exception]) -> None:
    with pytest.raises(error):
        await adapter(lambda r: httpx.Response(status, json=body)).generate(
            LLMRequest(model="m", messages=[UserMessage(content="x")])
        )


async def test_blocked_prompt_is_content_filtered() -> None:
    with pytest.raises(errors.ContentFiltered):
        await adapter(lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})).generate(
            LLMRequest(model="m", messages=[UserMessage(content="x")])
        )
