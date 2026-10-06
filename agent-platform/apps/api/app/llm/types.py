"""Canonical, provider-neutral message and request format.

Orchestration code only ever sees these types. Adapters translate both ways.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class ToolCallRequest(BaseModel):
    """A tool call proposed by the model."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class SystemMessage(BaseModel):
    role: Literal["system"] = "system"
    content: str


class UserMessage(BaseModel):
    role: Literal["user"] = "user"
    content: str


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str | None = None
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    # Opaque provider content (e.g. signed thinking blocks) replayed verbatim to the same
    # provider/model on the next request. Never rendered to users.
    provider_state: dict[str, Any] | None = Field(default=None, exclude=False)


class ToolResultMessage(BaseModel):
    """Tool output. Always delimited from instructions: untrusted data."""

    role: Literal["tool"] = "tool"
    tool_call_id: str
    name: str
    content: str
    is_error: bool = False


Message = Annotated[
    SystemMessage | UserMessage | AssistantMessage | ToolResultMessage, Field(discriminator="role")
]


class ToolDefinition(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})


class ToolChoice(StrEnum):
    auto = "auto"
    none = "none"
    required = "required"


class ResponseFormat(BaseModel):
    """Structured output request: the model must return JSON matching `json_schema`."""

    name: str = "output"
    json_schema: dict[str, Any]


class LLMRequest(BaseModel):
    model: str
    messages: list[Message]
    tools: list[ToolDefinition] = Field(default_factory=list)
    tool_choice: ToolChoice = ToolChoice.auto
    temperature: float | None = None
    max_tokens: int | None = None
    response_format: ResponseFormat | None = None
    # namespaced per provider type, e.g. {"openai": {...}, "fake": {...}}; adapters read only their own key
    extras: dict[str, Any] = Field(default_factory=dict)


class StopReason(StrEnum):
    end_turn = "end_turn"
    tool_use = "tool_use"
    max_tokens = "max_tokens"
    content_filter = "content_filter"
    stop_sequence = "stop_sequence"
    other = "other"


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMResponse(BaseModel):
    message: AssistantMessage
    stop_reason: StopReason
    usage: Usage = Field(default_factory=Usage)
    model: str
    latency_ms: int = 0


class LLMStreamEvent(BaseModel):
    type: Literal["text_delta", "tool_call", "done"]
    text: str | None = None
    tool_call: ToolCallRequest | None = None
    response: LLMResponse | None = None
