"""LangGraph state for compiled pipelines. Merge reducers let parallel branches write safely."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from pydantic import TypeAdapter

from app.llm.types import Message


def merge_dict(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    return {**(left or {}), **(right or {})}


class GraphState(TypedDict, total=False):
    input: dict[str, Any]
    outputs: Annotated[dict[str, Any], merge_dict]
    node_status: Annotated[dict[str, str], merge_dict]
    agents: Annotated[dict[str, Any], merge_dict]


# node_status values beyond NodeStatus: a node that failed but routed to its error edge.
FAILED_HANDLED = "failed_handled"

_MESSAGES = TypeAdapter(list[Message])


def dump_messages(messages: list[Any]) -> list[dict[str, Any]]:
    return _MESSAGES.dump_python(messages, mode="json")  # type: ignore[no-any-return]


def load_messages(raw: list[dict[str, Any]]) -> list[Any]:
    return list(_MESSAGES.validate_python(raw))
