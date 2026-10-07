"""Anthropic adapter: canonical <-> Messages API translation and SDK error mapping."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import anthropic
import httpx2 as httpx  # the anthropic SDK is built on httpx2
import pytest
from anthropic.types.beta import BetaMessage

from app.core.enums import ErrorCode
from app.llm import errors
from app.llm.adapters.anthropic import (
    AnthropicAdapter,
    from_anthropic_message,
    to_anthropic_messages,
)
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

TOOL = ToolDefinition(
    name="demo_jobs__get_job",
    description="Get a job",
    input_schema={"type": "object", "properties": {"job_id": {"type": "string"}}},
)


def _request(**kwargs: Any) -> LLMRequest:
    base: dict[str, Any] = {"model": "claude-opus-5-5", "messages": [UserMessage(content="hi")]}
    return LLMRequest(**{**base, **kwargs})


def _message_json(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": "Hello"}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": 3},
        **overrides,
    }


def _adapter(handler: Callable[[httpx.Request], httpx.Response]) -> AnthropicAdapter:
    client = anthropic.AsyncAnthropic(
        api_key="test-key", max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    return AnthropicAdapter(ProviderConfig(provider_type="anthropic", base_url=None, api_key="test-key"), client)


def test_system_messages_become_top_level() -> None:
    req = _request(
        messages=[SystemMessage(content="Rule one."), SystemMessage(content="Rule two."), UserMessage(content="Go")]
    )
    system, messages = to_anthropic_messages(req)
    assert system == "Rule one.\n\nRule two."
    assert messages == [{"role": "user", "content": [{"type": "text", "text": "Go"}]}]
    assert all(m["role"] != "system" for m in messages)


def test_consecutive_tool_results_merge_into_one_user_turn() -> None:
    req = _request(
        messages=[
            UserMessage(content="Find two jobs"),
            AssistantMessage(
                content="Looking",
                tool_calls=[
                    ToolCallRequest(id="tu_1", name="a", arguments={"x": 1}),
                    ToolCallRequest(id="tu_2", name="b", arguments={}),
                ],
            ),
            ToolResultMessage(tool_call_id="tu_1", name="a", content="one"),
            ToolResultMessage(tool_call_id="tu_2", name="b", content="boom", is_error=True),
            UserMessage(content="And now?"),
        ]
    )
    _, messages = to_anthropic_messages(req)
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "user"]
    assert messages[1]["content"] == [
        {"type": "text", "text": "Looking"},
        {"type": "tool_use", "id": "tu_1", "name": "a", "input": {"x": 1}},
        {"type": "tool_use", "id": "tu_2", "name": "b", "input": {}},
    ]
    assert messages[2]["content"] == [
        {"type": "tool_result", "tool_use_id": "tu_1", "content": "one", "is_error": False},
        {"type": "tool_result", "tool_use_id": "tu_2", "content": "boom", "is_error": True},
    ]
    assert messages[3]["content"] == [{"type": "text", "text": "And now?"}]


def test_provider_state_replays_thinking_with_edited_tool_input() -> None:
    stored = [
        {"type": "thinking", "thinking": "plan", "signature": "sig-abc"},
        {"type": "text", "text": "Submitting"},
        {"type": "tool_use", "id": "tu_9", "name": "demo_jobs__submit_proposal", "input": {"hourly_rate": 85}},
    ]
    edited = AssistantMessage(
        content="Submitting",
        tool_calls=[ToolCallRequest(id="tu_9", name="demo_jobs__submit_proposal", arguments={"hourly_rate": 99})],
        provider_state={"provider": "anthropic", "model": "claude-opus-5-5", "content": stored},
    )
    _, messages = to_anthropic_messages(_request(messages=[UserMessage(content="go"), edited]))
    blocks = messages[1]["content"]
    assert blocks[0] == {"type": "thinking", "thinking": "plan", "signature": "sig-abc"}  # verbatim
    assert blocks[2]["input"] == {"hourly_rate": 99}
    assert stored[2]["input"] == {"hourly_rate": 85}, "stored provider state must not be mutated"


def test_foreign_provider_state_is_ignored() -> None:
    msg = AssistantMessage(content="hi", provider_state={"provider": "openai", "content": [{"type": "x"}]})
    _, messages = to_anthropic_messages(_request(messages=[UserMessage(content="a"), msg]))
    assert messages[1]["content"] == [{"type": "text", "text": "hi"}]


def test_build_params_tool_choice_format_thinking_and_sampling() -> None:
    adapter = AnthropicAdapter(ProviderConfig(provider_type="anthropic", base_url=None, api_key="k"), client=object())  # type: ignore[arg-type]
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    params = adapter.build_params(
        _request(
            messages=[SystemMessage(content="sys"), UserMessage(content="u")],
            tools=[TOOL],
            tool_choice=ToolChoice.required,
            response_format=ResponseFormat(json_schema=schema),
            temperature=0.3,
            extras={
                "anthropic": {
                    "thinking": {"type": "adaptive"},
                    "output_config": {"effort": "medium"},
                    "fallbacks": "default",
                },
                "openai": {"ignored": True},
            },
        )
    )
    assert params["system"] == "sys"
    assert params["max_tokens"] == 16000
    assert params["tool_choice"] == {"type": "auto"}  # forced choice is not sent
    assert params["tools"] == [{"name": TOOL.name, "description": "Get a job", "input_schema": TOOL.input_schema}]
    assert params["output_config"] == {"effort": "medium", "format": {"type": "json_schema", "schema": schema}}
    assert params["thinking"] == {"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}}
    assert set(params["betas"]) == {"thinking-binding-controls-2026-08-01", "server-side-fallback-2026-07-01"}
    assert "temperature" not in params and "extra_body" not in params
    assert "ignored" not in json.dumps(params)

    none_choice = adapter.build_params(
        _request(
            tools=[TOOL], tool_choice=ToolChoice.none, temperature=0.3, extras={"anthropic": {"allow_sampling": True}}
        )
    )
    assert none_choice["tool_choice"] == {"type": "none"}
    assert none_choice["extra_body"] == {"temperature": 0.3}
    assert "system" not in none_choice and "betas" not in none_choice and "output_config" not in none_choice


def test_from_anthropic_message_keeps_thinking_for_replay() -> None:
    message = BetaMessage.model_validate(
        _message_json(
            content=[
                {"type": "thinking", "thinking": "hmm", "signature": "sig"},
                {"type": "text", "text": "Calling "},
                {"type": "text", "text": "a tool"},
                {"type": "tool_use", "id": "tu_1", "name": "demo__t", "input": {"a": 1}},
            ],
            stop_reason="tool_use",
        )
    )
    response = from_anthropic_message(message, latency_ms=42)
    assert response.message.content == "Calling a tool"
    assert response.message.tool_calls == [ToolCallRequest(id="tu_1", name="demo__t", arguments={"a": 1})]
    assert response.stop_reason == StopReason.tool_use
    assert (response.usage.input_tokens, response.usage.output_tokens, response.latency_ms) == (12, 3, 42)
    state = response.message.provider_state
    assert state is not None and state["provider"] == "anthropic"
    assert [b["type"] for b in state["content"]] == ["thinking", "text", "text", "tool_use"]
    assert state["content"][0]["signature"] == "sig"


async def test_generate_round_trip_over_http() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta")
        return httpx.Response(200, json=_message_json())

    adapter = _adapter(handler)
    response = await adapter.generate(
        _request(
            messages=[SystemMessage(content="S"), UserMessage(content="U")],
            extras={"anthropic": {"thinking": {"type": "adaptive"}}},
        )
    )
    assert response.message.content == "Hello" and response.stop_reason == StopReason.end_turn
    assert seen["path"] == "/v1/messages"
    assert seen["body"]["system"] == "S"
    assert seen["body"]["thinking"]["block_binding"] == {"prefix_mismatch_behavior": "drop_block"}
    assert "thinking-binding-controls-2026-08-01" in seen["beta"]


@pytest.mark.parametrize(
    ("status", "body", "expected", "retryable"),
    [
        (
            429,
            {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}},
            errors.RateLimitedError,
            True,
        ),
        (
            401,
            {"type": "error", "error": {"type": "authentication_error", "message": "bad key"}},
            errors.AuthFailed,
            False,
        ),
        (403, {"type": "error", "error": {"type": "permission_error", "message": "no"}}, errors.AuthFailed, False),
        (
            413,
            {"type": "error", "error": {"type": "request_too_large", "message": "big"}},
            errors.ContextTooLong,
            False,
        ),
        (
            400,
            {
                "type": "error",
                "error": {"type": "invalid_request_error", "message": "prompt is too long: 300000 tokens > 200000"},
            },
            errors.ContextTooLong,
            False,
        ),
        (
            400,
            {"type": "error", "error": {"type": "invalid_request_error", "message": "bad field"}},
            errors.InvalidRequest,
            False,
        ),
        (500, {"type": "error", "error": {"type": "api_error", "message": "oops"}}, errors.ProviderUnavailable, True),
        (
            529,
            {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}},
            errors.ProviderUnavailable,
            True,
        ),
    ],
)
async def test_error_mapping(
    status: int, body: dict[str, Any], expected: type[errors.LLMError], retryable: bool
) -> None:
    adapter = _adapter(lambda _: httpx.Response(status, json=body))
    with pytest.raises(expected) as info:
        await adapter.generate(_request())
    assert info.value.retryable is retryable
    assert info.value.details["provider"] == "anthropic"


async def test_connection_and_timeout_errors() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(errors.ProviderUnavailable):
        await _adapter(refuse).generate(_request())
    with pytest.raises(errors.TimeoutError_) as info:
        await _adapter(slow).generate(_request())
    assert info.value.code == ErrorCode.llm_timeout


async def test_refusal_without_content_is_content_filtered() -> None:
    adapter = _adapter(lambda _: httpx.Response(200, json=_message_json(content=[], stop_reason="refusal")))
    with pytest.raises(errors.ContentFiltered):
        await adapter.generate(_request())
