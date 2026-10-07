"""Google Gemini adapter (Generative Language API, `models/{model}:generateContent`) over httpx.

Translation notes:
* System messages become `systemInstruction`; assistant turns are role `model`; tool results
  are `functionResponse` parts in a `user` turn, merged when consecutive.
* Tool schemas are sent as full JSON Schema via `parametersJsonSchema`; structured output uses
  `responseJsonSchema` with `responseMimeType: application/json`.
* Gemini attaches `thoughtSignature` to function-call parts. The raw parts are stored in
  `AssistantMessage.provider_state` and replayed verbatim (with any human-edited arguments
  applied) so multi-step tool loops keep working.
* `required` tool choice maps to function-calling mode `ANY`, `none` to `NONE`.
* Not expressible: images, files, code execution and grounding tools.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.llm import errors
from app.llm.base import HttpAdapter
from app.llm.types import (
    AssistantMessage,
    LLMRequest,
    LLMResponse,
    StopReason,
    SystemMessage,
    ToolCallRequest,
    ToolChoice,
    ToolResultMessage,
    Usage,
    UserMessage,
)

_FINISH = {
    "STOP": StopReason.end_turn,
    "MAX_TOKENS": StopReason.max_tokens,
    "SAFETY": StopReason.content_filter,
    "RECITATION": StopReason.content_filter,
    "PROHIBITED_CONTENT": StopReason.content_filter,
    "BLOCKLIST": StopReason.content_filter,
    "SPII": StopReason.content_filter,
}
_MODES = {ToolChoice.auto: "AUTO", ToolChoice.required: "ANY", ToolChoice.none: "NONE"}


def _response_object(content: str) -> dict[str, Any]:
    try:
        value = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {"result": content}
    return value if isinstance(value, dict) else {"result": value}


def _replay_parts(parts: list[dict[str, Any]], msg: AssistantMessage) -> list[dict[str, Any]]:
    args_by_index: dict[int, dict[str, Any]] = {i: c.arguments for i, c in enumerate(msg.tool_calls)}
    out, call_index = [], 0
    for part in parts:
        if "functionCall" in part:
            args = args_by_index.get(call_index)
            call_index += 1
            if args is not None:
                part = {**part, "functionCall": {**part["functionCall"], "args": args}}
        out.append(part)
    return out


def to_gemini_contents(req: LLMRequest) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    system: list[str] = []
    contents: list[dict[str, Any]] = []
    names_by_id: dict[str, str] = {}
    for msg in req.messages:
        if isinstance(msg, SystemMessage):
            system.append(msg.content)
        elif isinstance(msg, UserMessage):
            contents.append({"role": "user", "parts": [{"text": msg.content}]})
        elif isinstance(msg, AssistantMessage):
            for call in msg.tool_calls:
                names_by_id[call.id] = call.name
            state = msg.provider_state or {}
            if state.get("provider") == "gemini" and state.get("parts"):
                parts = _replay_parts(state["parts"], msg)
            else:
                parts = [{"text": msg.content}] if msg.content else []
                parts += [{"functionCall": {"name": c.name, "args": c.arguments}} for c in msg.tool_calls]
            contents.append({"role": "model", "parts": parts or [{"text": ""}]})
        elif isinstance(msg, ToolResultMessage):
            part = {
                "functionResponse": {
                    "name": names_by_id.get(msg.tool_call_id, msg.name),
                    "response": _response_object(msg.content),
                }
            }
            prev = contents[-1] if contents else None
            if prev and prev["role"] == "user" and all("functionResponse" in p for p in prev["parts"]):
                prev["parts"].append(part)
            else:
                contents.append({"role": "user", "parts": [part]})
    instruction = {"parts": [{"text": "\n\n".join(system)}]} if system else None
    return instruction, contents


class GeminiAdapter(HttpAdapter):
    provider_name = "gemini"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"

    def headers(self) -> dict[str, str]:
        headers = super().headers()
        if self.config.api_key:
            headers["x-goog-api-key"] = self.config.api_key
        return headers

    def build_payload(self, req: LLMRequest) -> dict[str, Any]:
        instruction, contents = to_gemini_contents(req)
        payload: dict[str, Any] = {"contents": contents}
        if instruction:
            payload["systemInstruction"] = instruction
        if req.tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {"name": t.name, "description": t.description[:1024], "parametersJsonSchema": t.input_schema}
                        for t in req.tools
                    ]
                }
            ]
            payload["toolConfig"] = {"functionCallingConfig": {"mode": _MODES[req.tool_choice]}}
        generation: dict[str, Any] = {}
        if req.temperature is not None:
            generation["temperature"] = req.temperature
        if req.max_tokens is not None:
            generation["maxOutputTokens"] = req.max_tokens
        if req.response_format is not None:
            generation["responseMimeType"] = "application/json"
            generation["responseJsonSchema"] = req.response_format.json_schema
        extras = dict(req.extras.get("gemini") or {})
        generation.update(extras.pop("generationConfig", {}) or {})
        if generation:
            payload["generationConfig"] = generation
        payload.update(extras)
        return payload

    async def generate(self, req: LLMRequest) -> LLMResponse:
        body, latency_ms = await self.post_json(f"/models/{req.model}:generateContent", self.build_payload(req))
        return self.parse_response(body, latency_ms, req.model)

    @staticmethod
    def parse_response(body: dict[str, Any], latency_ms: int, model: str) -> LLMResponse:
        candidates = body.get("candidates") or []
        if not candidates:
            reason = (body.get("promptFeedback") or {}).get("blockReason")
            if reason:
                raise errors.ContentFiltered(f"Gemini blocked the prompt: {reason}", details={"provider": "gemini"})
            raise errors.ProviderUnavailable("Gemini returned no candidates", details={"provider": "gemini"})
        candidate = candidates[0]
        parts: list[dict[str, Any]] = list((candidate.get("content") or {}).get("parts") or [])
        texts = [p["text"] for p in parts if "text" in p and not p.get("thought")]
        calls = [
            ToolCallRequest(
                id=p["functionCall"].get("id") or f"call_{i}",
                name=p["functionCall"]["name"],
                arguments=dict(p["functionCall"].get("args") or {}),
            )
            for i, p in enumerate(parts)
            if "functionCall" in p
        ]
        finish = candidate.get("finishReason") or ""
        stop = StopReason.tool_use if calls else _FINISH.get(finish, StopReason.other)
        if stop == StopReason.content_filter and not texts and not calls:
            raise errors.ContentFiltered(f"Gemini stopped for {finish}", details={"provider": "gemini"})
        usage = body.get("usageMetadata") or {}
        replay = [p for p in parts if not p.get("thought")]
        return LLMResponse(
            message=AssistantMessage(
                content="".join(texts) or None,
                tool_calls=calls,
                provider_state={"provider": "gemini", "model": model, "parts": replay},
            ),
            stop_reason=stop,
            usage=Usage(
                input_tokens=int(usage.get("promptTokenCount", 0)),
                output_tokens=int(usage.get("candidatesTokenCount", 0)) + int(usage.get("thoughtsTokenCount", 0)),
            ),
            model=body.get("modelVersion") or model,
            latency_ms=latency_ms,
        )

    def classify(self, response: httpx.Response) -> errors.LLMError:
        message = self.error_message(response)
        if response.status_code == 400 and "token" in message.lower() and "exceed" in message.lower():
            return errors.ContextTooLong(message, details={"provider": "gemini"})
        if response.status_code == 400 and "API key" in message:
            return errors.AuthFailed(message, details={"provider": "gemini"})
        return errors.from_http_status(response.status_code, message, provider="gemini")

    async def health(self, model: str | None = None) -> str:
        try:
            async with self.client() as client:
                response = await client.get("/models", params={"pageSize": 50})
        except httpx.TransportError as exc:
            raise errors.ProviderUnavailable("Gemini is unreachable", details={"provider": "gemini"}) from exc
        if response.status_code >= 400:
            raise self.classify(response)
        names = [m.get("name", "").removeprefix("models/") for m in (response.json() or {}).get("models", [])]
        return f"Connected. {len(names)} models visible" + (f", e.g. {names[0]}" if names else "")
