"""Context assembly within a token budget.

Order of preference: system prompt, the task input (first user message), tool
definitions, recent tool results, then older steps. Large tool results are truncated with
a pointer to the stored full result (`tool_calls.result`). When still over budget, older
tool results are replaced by a one-line placeholder. Summarisation can be added by
implementing `Summarizer` and passing it in; the default only truncates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from app.llm.types import AssistantMessage, Message, ToolDefinition, ToolResultMessage

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def message_tokens(message: Message) -> int:
    if isinstance(message, AssistantMessage):
        body = (message.content or "") + json.dumps([c.model_dump() for c in message.tool_calls])
        return estimate_tokens(body) + 4
    return estimate_tokens(message.content) + 4


class Summarizer(Protocol):
    async def summarize(self, messages: list[Message]) -> str: ...


@dataclass(frozen=True)
class ContextBudget:
    max_input_tokens: int
    max_tool_result_chars: int = 12_000
    keep_recent_tool_results: int = 4


def truncate_tool_result(message: ToolResultMessage, limit: int, pointer: str | None) -> ToolResultMessage:
    if len(message.content) <= limit:
        return message
    note = f"\n…[truncated {len(message.content) - limit} chars"
    note += f"; full result stored as {pointer}]" if pointer else "]"
    return message.model_copy(update={"content": message.content[:limit] + note})


def fit_messages(
    messages: list[Message],
    tools: list[ToolDefinition],
    budget: ContextBudget,
    pointers: dict[str, str] | None = None,
) -> list[Message]:
    """Return a copy of `messages` that fits the budget. Never drops system/first user/assistant turns."""
    pointers = pointers or {}
    out: list[Message] = [
        truncate_tool_result(m, budget.max_tool_result_chars, pointers.get(m.tool_call_id))
        if isinstance(m, ToolResultMessage)
        else m
        for m in messages
    ]
    tool_tokens = sum(estimate_tokens(json.dumps(t.model_dump())) for t in tools)

    def total() -> int:
        return tool_tokens + sum(message_tokens(m) for m in out)

    if total() <= budget.max_input_tokens:
        return out
    tool_positions = [i for i, m in enumerate(out) if isinstance(m, ToolResultMessage)]
    for i in tool_positions[: max(0, len(tool_positions) - budget.keep_recent_tool_results)]:
        msg = out[i]
        assert isinstance(msg, ToolResultMessage)
        pointer = pointers.get(msg.tool_call_id)
        out[i] = msg.model_copy(
            update={
                "content": f"[older result omitted to fit the context window{'; stored as ' + pointer if pointer else ''}]"
            }
        )
        if total() <= budget.max_input_tokens:
            return out
    return out
