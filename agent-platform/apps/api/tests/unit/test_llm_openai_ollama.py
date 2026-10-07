"""OpenAI Chat Completions and Ollama adapters over httpx.MockTransport."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.llm import errors
from app.llm.adapters.ollama import OllamaAdapter
from app.llm.adapters.openai import OpenAIAdapter, parse_arguments
from app.llm.base import ProviderConfig
from app.llm.registry import build_provider, estimate_cost
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
    Usage,
    UserMessage,
)

TOOL = ToolDefinition(name="demo_jobs__get_job", description="d" * 2000,
                      input_schema={"type": "object", "properties": {"job_id": {"type": "string"}},
                                    "required": ["job_id"]})
HISTORY = [
    SystemMessage(content="Be brief."),
    UserMessage(content="Read job-101"),
    AssistantMessage(content=None, tool_calls=[ToolCallRequest(id="call_1", name=TOOL.name,
                                                               arguments={"job_id": "job-101"})],
                     provider_state={"provider": "anthropic", "content": [{"type": "thinking"}]}),
    ToolResultMessage(tool_call_id="call_1", name=TOOL.name, content='{"id": "job-101"}'),
]
Handler = Callable[[httpx.Request], httpx.Response]


def _openai(handler: Handler, **config: Any) -> OpenAIAdapter:
    cfg = ProviderConfig(provider_type="openai", base_url=config.get("base_url"), api_key=config.get("api_key"),
                         metadata=config.get("metadata", {}))
    return OpenAIAdapter(cfg, transport=httpx.MockTransport(handler))


def _ollama(handler: Handler) -> OllamaAdapter:
    return OllamaAdapter(ProviderConfig(provider_type="ollama", base_url="http://ollama:11434/"),
                         transport=httpx.MockTransport(handler))


def _capture(response: dict[str, Any], seen: dict[str, Any]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=response)

    return handler


OPENAI_TOOL_RESPONSE = {
    "model": "gpt-4.1-mini-2026", "usage": {"prompt_tokens": 30, "completion_tokens": 7},
    "choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_2", "type": "function", "function": {"name": TOOL.name, "arguments": '{"job_id": "job-102"}'}},
    ]}}],
}


async def test_openai_request_translation_and_response() -> None:
    seen: dict[str, Any] = {}
    adapter = _openai(_capture(OPENAI_TOOL_RESPONSE, seen), api_key="sk-abc", metadata={"organization": "org-1"})
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    response = await adapter.generate(LLMRequest(
        model="gpt-4.1-mini", messages=HISTORY, tools=[TOOL], tool_choice=ToolChoice.required, temperature=0.2,
        max_tokens=256, response_format=ResponseFormat(name="verdict", json_schema=schema),
        extras={"openai": {"seed": 7}, "anthropic": {"thinking": {}}},
    ))
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["headers"]["authorization"] == "Bearer sk-abc"
    assert seen["headers"]["openai-organization"] == "org-1"
    body = seen["body"]
    assert body["messages"] == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Read job-101"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": TOOL.name, "arguments": json.dumps({"job_id": "job-101"})}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": '{"id": "job-101"}'},
    ]
    assert body["tools"] == [{"type": "function", "function": {
        "name": TOOL.name, "description": "d" * 1024, "parameters": TOOL.input_schema}}]
    assert body["tool_choice"] == "required"
    assert (body["temperature"], body["max_completion_tokens"], body["seed"]) == (0.2, 256, 7)
    assert body["response_format"] == {"type": "json_schema", "json_schema": {
        "name": "verdict", "schema": schema, "strict": False}}
    assert "thinking" not in json.dumps(body)

    assert response.message.tool_calls == [ToolCallRequest(id="call_2", name=TOOL.name,
                                                           arguments={"job_id": "job-102"})]
    assert response.stop_reason == StopReason.tool_use
    assert response.usage == Usage(input_tokens=30, output_tokens=7)
    assert response.model == "gpt-4.1-mini-2026"


async def test_openai_minimal_request_omits_optional_fields() -> None:
    seen: dict[str, Any] = {}
    reply = {"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]}
    adapter = _openai(_capture(reply, seen), base_url="http://vllm:8000/v1/")
    response = await adapter.generate(LLMRequest(model="m", messages=[UserMessage(content="hi")]))
    assert seen["url"] == "http://vllm:8000/v1/chat/completions"
    assert "authorization" not in seen["headers"]
    assert set(seen["body"]) == {"model", "messages"}
    assert response.stop_reason == StopReason.max_tokens and response.model == "m"


def test_parse_arguments_edge_cases() -> None:
    assert parse_arguments(None) == {}
    assert parse_arguments("") == {}
    assert parse_arguments({"a": 1}) == {"a": 1}
    assert parse_arguments("[1, 2]") == {"value": [1, 2]}
    assert parse_arguments("{not json") == {"__invalid_json__": "{not json"}


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (429, {"error": {"message": "Rate limit reached"}}, errors.RateLimitedError),
        (401, {"error": {"message": "Incorrect API key"}}, errors.AuthFailed),
        (403, {"error": {"message": "Forbidden"}}, errors.AuthFailed),
        (408, {"error": {"message": "timeout"}}, errors.TimeoutError_),
        (413, {"error": {"message": "too big"}}, errors.ContextTooLong),
        (400, {"error": {"message": "This model's maximum context length is 8192 tokens",
                         "code": "context_length_exceeded"}}, errors.ContextTooLong),
        (400, {"error": {"message": "Rejected by content_filter"}}, errors.ContentFiltered),
        (400, {"error": {"message": "Unknown parameter"}}, errors.InvalidRequest),
        (404, {"error": {"message": "model not found"}}, errors.InvalidRequest),
        (500, "<html>upstream</html>", errors.ProviderUnavailable),
        (503, {"error": "overloaded"}, errors.ProviderUnavailable),
    ],
)
async def test_openai_error_mapping(status: int, body: Any, expected: type[errors.LLMError]) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=body)

    with pytest.raises(expected) as info:
        await _openai(handler).generate(LLMRequest(model="m", messages=[UserMessage(content="hi")]))
    assert info.value.details["provider"] == "openai"
    assert info.value.retryable is (expected in (errors.RateLimitedError, errors.TimeoutError_,
                                                 errors.ProviderUnavailable))


async def test_transport_failures_and_empty_choices() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    req = LLMRequest(model="m", messages=[UserMessage(content="hi")])
    with pytest.raises(errors.ProviderUnavailable):
        await _openai(refuse).generate(req)
    with pytest.raises(errors.TimeoutError_):
        await _openai(slow).generate(req)
    with pytest.raises(errors.ProviderUnavailable):
        await _openai(lambda _: httpx.Response(200, json={"choices": []})).generate(req)
    with pytest.raises(errors.TimeoutError_):
        await _ollama(slow).generate(req)


async def test_ollama_translation_and_synthesised_ids() -> None:
    seen: dict[str, Any] = {}
    reply = {"model": "llama3.2", "done_reason": "stop", "prompt_eval_count": 40, "eval_count": 9,
             "message": {"role": "assistant", "content": "", "tool_calls": [
                 {"function": {"name": TOOL.name, "arguments": {"job_id": "job-103"}}},
                 {"function": {"name": TOOL.name, "arguments": '{"job_id": "job-104"}'}}]}}
    schema = {"type": "object"}
    response = await _ollama(_capture(reply, seen)).generate(LLMRequest(
        model="llama3.2", messages=HISTORY, tools=[TOOL], temperature=0.1, max_tokens=64,
        response_format=ResponseFormat(json_schema=schema), extras={"ollama": {"keep_alive": "5m"}}))
    assert seen["url"] == "http://ollama:11434/api/chat"
    body = seen["body"]
    assert body["stream"] is False
    assert body["messages"][2] == {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": TOOL.name, "arguments": {"job_id": "job-101"}}}]}
    assert body["messages"][3] == {"role": "tool", "content": '{"id": "job-101"}', "tool_name": TOOL.name}
    assert body["tools"][0]["function"]["name"] == TOOL.name
    assert body["options"] == {"temperature": 0.1, "num_predict": 64}
    assert body["format"] == schema and body["keep_alive"] == "5m"

    assert [c.id for c in response.message.tool_calls] == ["call_0", "call_1"]
    assert [c.arguments for c in response.message.tool_calls] == [{"job_id": "job-103"}, {"job_id": "job-104"}]
    assert response.message.content is None
    assert response.stop_reason == StopReason.tool_use
    assert response.usage == Usage(input_tokens=40, output_tokens=9)


async def test_ollama_errors_and_length_stop() -> None:
    req = LLMRequest(model="llama3.2", messages=[UserMessage(content="hi")])
    with pytest.raises(errors.InvalidRequest):
        await _ollama(lambda _: httpx.Response(404, json={"error": "model 'llama3.2' not found"})).generate(req)
    with pytest.raises(errors.ProviderUnavailable):
        await _ollama(lambda _: httpx.Response(500, json={"error": "crash"})).generate(req)
    reply = {"message": {"content": "cut"}, "done_reason": "length"}
    response = await _ollama(lambda _: httpx.Response(200, json=reply)).generate(req)
    assert response.stop_reason == StopReason.max_tokens and response.message.content == "cut"


def test_registry_and_cost() -> None:
    assert isinstance(build_provider(ProviderConfig(provider_type="openai", base_url=None)), OpenAIAdapter)
    with pytest.raises(ValueError, match="No adapter"):
        build_provider(ProviderConfig(provider_type="mystery", base_url=None))
    assert str(estimate_cost(Usage(input_tokens=1_000_000, output_tokens=500_000), "4", "20")) == "14.000000"
    assert str(estimate_cost(Usage(input_tokens=1, output_tokens=0), "0.4", "1.6")) == "0.000000"
