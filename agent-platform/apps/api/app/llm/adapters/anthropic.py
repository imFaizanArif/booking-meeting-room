"""Anthropic Messages API adapter, built on the official `anthropic` SDK.

Translation notes:
* System messages become the top-level `system`; consecutive tool results are merged into
  one user turn (parallel tool calls must be answered in a single message).
* Signed thinking blocks are stored in `AssistantMessage.provider_state` and replayed
  verbatim on the next request. When the orchestrator rewrites an earlier turn (edit +
  approve), later blocks no longer match their prefix, so requests with thinking enabled
  set `block_binding.prefix_mismatch_behavior = "drop_block"` and the API drops them
  instead of rejecting the request.
* Forced tool choice (`required`) is sent as `auto`: current models reject `any`/`tool`.
* Structured output uses `output_config.format` (json_schema).
* Sampling parameters are only sent when the model opts in via
  `extras.anthropic.allow_sampling` (current models reject `temperature`).
* Anything the canonical format cannot express (images, documents, server tools) is not
  supported by this adapter.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import anthropic

from app.llm import errors
from app.llm.base import ProviderConfig
from app.llm.types import (
    AssistantMessage,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    StopReason,
    SystemMessage,
    ToolCallRequest,
    ToolChoice,
    ToolResultMessage,
    Usage,
    UserMessage,
)

_STOP = {
    "end_turn": StopReason.end_turn,
    "tool_use": StopReason.tool_use,
    "max_tokens": StopReason.max_tokens,
    "stop_sequence": StopReason.stop_sequence,
    "refusal": StopReason.content_filter,
}
_BINDING_BETA = "thinking-binding-controls-2026-08-01"
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
DEFAULT_MAX_TOKENS = 16000


def to_anthropic_messages(req: LLMRequest) -> tuple[str | None, list[dict[str, Any]]]:
    system_parts: list[str] = []
    out: list[dict[str, Any]] = []
    for msg in req.messages:
        if isinstance(msg, SystemMessage):
            system_parts.append(msg.content)
        elif isinstance(msg, UserMessage):
            out.append({"role": "user", "content": [{"type": "text", "text": msg.content}]})
        elif isinstance(msg, AssistantMessage):
            state = msg.provider_state or {}
            if state.get("provider") == "anthropic" and state.get("content"):
                blocks = _replay_blocks(state["content"], msg)
            else:
                blocks = []
                if msg.content:
                    blocks.append({"type": "text", "text": msg.content})
                blocks.extend(
                    {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments} for c in msg.tool_calls
                )
            out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
        elif isinstance(msg, ToolResultMessage):
            block = {
                "type": "tool_result",
                "tool_use_id": msg.tool_call_id,
                "content": msg.content,
                "is_error": msg.is_error,
            }
            if out and out[-1]["role"] == "user" and all(b.get("type") == "tool_result" for b in out[-1]["content"]):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
    return ("\n\n".join(system_parts) or None), out


def _replay_blocks(blocks: list[dict[str, Any]], msg: AssistantMessage) -> list[dict[str, Any]]:
    """Replay stored blocks, applying canonical edits (edited tool arguments) to tool_use blocks."""
    args_by_id = {c.id: c.arguments for c in msg.tool_calls}
    replayed = []
    for block in blocks:
        if block.get("type") == "tool_use" and block.get("id") in args_by_id:
            block = {**block, "input": args_by_id[block["id"]]}
        replayed.append(block)
    return replayed


def to_anthropic_tools(req: LLMRequest) -> list[dict[str, Any]]:
    return [{"name": t.name, "description": t.description[:1024], "input_schema": t.input_schema} for t in req.tools]


def from_anthropic_message(message: Any, latency_ms: int) -> LLMResponse:
    text_parts: list[str] = []
    calls: list[ToolCallRequest] = []
    raw_blocks: list[dict[str, Any]] = []
    for block in message.content:
        btype = getattr(block, "type", None)
        if btype == "text":
            text_parts.append(block.text)
        elif btype == "tool_use":
            calls.append(ToolCallRequest(id=block.id, name=block.name, arguments=dict(block.input or {})))
        if btype in ("text", "tool_use", "thinking", "redacted_thinking"):
            raw_blocks.append(block.model_dump(mode="json", exclude_none=True))
    usage = Usage(
        input_tokens=getattr(message.usage, "input_tokens", 0) or 0,
        output_tokens=getattr(message.usage, "output_tokens", 0) or 0,
    )
    return LLMResponse(
        message=AssistantMessage(
            content="".join(text_parts) or None,
            tool_calls=calls,
            provider_state={"provider": "anthropic", "model": message.model, "content": raw_blocks},
        ),
        stop_reason=_STOP.get(message.stop_reason or "", StopReason.other),
        usage=usage,
        model=message.model,
        latency_ms=latency_ms,
    )


class AnthropicAdapter:
    provider_name = "anthropic"

    def __init__(self, config: ProviderConfig, client: anthropic.AsyncAnthropic | None = None) -> None:
        self.config = config
        self._client = client or anthropic.AsyncAnthropic(
            api_key=config.api_key,
            base_url=config.base_url or None,
            timeout=config.timeout_s,
            max_retries=0,  # retries are owned by the execution engine
        )

    def build_params(self, req: LLMRequest) -> dict[str, Any]:
        system, messages = to_anthropic_messages(req)
        opts: dict[str, Any] = dict(req.extras.get("anthropic") or {})
        params: dict[str, Any] = {
            "model": req.model,
            "max_tokens": req.max_tokens or DEFAULT_MAX_TOKENS,
            "messages": messages,
        }
        betas: list[str] = []
        extra_body: dict[str, Any] = {}
        if system:
            params["system"] = system
        if req.tools:
            params["tools"] = to_anthropic_tools(req)
            params["tool_choice"] = {"type": "none" if req.tool_choice == ToolChoice.none else "auto"}
        output_config: dict[str, Any] = dict(opts.get("output_config") or {})
        if req.response_format is not None:
            output_config["format"] = {"type": "json_schema", "schema": req.response_format.json_schema}
        if output_config:
            params["output_config"] = output_config
        thinking = opts.get("thinking")
        if thinking:
            params["thinking"] = {**thinking, "block_binding": {"prefix_mismatch_behavior": "drop_block"}}
            betas.append(_BINDING_BETA)
        if opts.get("fallbacks"):
            params["fallbacks"] = opts["fallbacks"]
            betas.append(_FALLBACK_BETA)
        if opts.get("allow_sampling") and req.temperature is not None:
            extra_body["temperature"] = req.temperature
        if betas:
            params["betas"] = betas
        if extra_body:
            params["extra_body"] = extra_body
        return params

    async def generate(self, req: LLMRequest) -> LLMResponse:
        params = self.build_params(req)
        started = time.perf_counter()
        try:
            message = await self._client.beta.messages.create(**params)
        except anthropic.APITimeoutError as exc:
            raise errors.TimeoutError_("Anthropic request timed out", details={"provider": "anthropic"}) from exc
        except anthropic.APIConnectionError as exc:
            raise errors.ProviderUnavailable("Anthropic is unreachable", details={"provider": "anthropic"}) from exc
        except anthropic.RateLimitError as exc:
            raise errors.RateLimitedError(exc.message, details={"provider": "anthropic"}) from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise errors.AuthFailed(exc.message, details={"provider": "anthropic"}) from exc
        except anthropic.RequestTooLargeError as exc:
            raise errors.ContextTooLong(exc.message, details={"provider": "anthropic"}) from exc
        except anthropic.BadRequestError as exc:
            body = exc.body if isinstance(exc.body, dict) else {}
            message_text = json.dumps(body)[:500] if body else exc.message
            if "prompt is too long" in message_text or ("context" in message_text and "exceed" in message_text):
                raise errors.ContextTooLong(exc.message, details={"provider": "anthropic"}) from exc
            raise errors.InvalidRequest(exc.message, details={"provider": "anthropic"}) from exc
        except anthropic.APIStatusError as exc:
            raise errors.from_http_status(exc.status_code, exc.message, provider="anthropic") from exc
        response = from_anthropic_message(message, int((time.perf_counter() - started) * 1000))
        if (
            response.stop_reason == StopReason.content_filter
            and not response.message.tool_calls
            and not response.message.content
        ):
            raise errors.ContentFiltered("The model declined this request", details={"provider": "anthropic"})
        return response

    async def stream(self, req: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        params = self.build_params(req)
        started = time.perf_counter()
        async with self._client.beta.messages.stream(**params) as stream:
            async for event in stream:
                if getattr(event, "type", None) == "text":
                    yield LLMStreamEvent(type="text_delta", text=event.text)
            final = await stream.get_final_message()
        response = from_anthropic_message(final, int((time.perf_counter() - started) * 1000))
        for call in response.message.tool_calls:
            yield LLMStreamEvent(type="tool_call", tool_call=call)
        yield LLMStreamEvent(type="done", response=response)

    async def health(self, model: str | None = None) -> str:
        try:
            page = await self._client.models.list(limit=5)
        except anthropic.AuthenticationError as exc:
            raise errors.AuthFailed("Anthropic rejected the API key", details={"provider": "anthropic"}) from exc
        except anthropic.APIConnectionError as exc:
            raise errors.ProviderUnavailable("Anthropic is unreachable", details={"provider": "anthropic"}) from exc
        except anthropic.APIStatusError as exc:
            raise errors.from_http_status(exc.status_code, exc.message, provider="anthropic") from exc
        ids = [m.id for m in page.data]
        return f"Connected. {len(ids)} models visible" + (f", e.g. {ids[0]}" if ids else "")
