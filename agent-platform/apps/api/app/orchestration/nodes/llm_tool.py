"""LLM node (single model call, optional structured output) and MCP Tool node."""

from __future__ import annotations

import json
from typing import Any

from app.core.enums import ErrorCode
from app.core.errors import AppError
from app.llm.context import ContextBudget, fit_messages
from app.llm.types import LLMRequest, ResponseFormat, SystemMessage, UserMessage
from app.orchestration.expressions import resolve
from app.orchestration.runtime import RuntimeContext
from app.orchestration.state import GraphState
from app.prompts.render import render
from app.schemas.pipeline_graph import AgentNode, LLMNode, MCPToolNode
from app.tools.router import RouteStatus
from app.tools.validation import argument_errors

_JSON_INSTRUCTION = (
    "Respond with only a JSON value that matches this JSON Schema. No prose, no code fences.\nSchema: {schema}"
)


class StructuredOutputInvalid(AppError):
    code = ErrorCode.validation_error
    retryable = True  # a fresh sample often fixes it


def system_prompt_for(node: LLMNode | AgentNode, rt: RuntimeContext, context: dict[str, Any]) -> str | None:
    prompt = rt.snapshot.prompts.get(node.id)
    if prompt is None:
        return None
    return render(prompt.body, context)


def parse_structured(text: str | None, schema: dict[str, Any]) -> Any:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("\n") + 1 :] if "\n" in raw else raw
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StructuredOutputInvalid("Model output is not valid JSON", details={"preview": raw[:300]}) from exc
    errors = argument_errors(schema, value) if schema.get("type", "object") == "object" else []
    if errors:
        raise StructuredOutputInvalid("Model output does not match the output schema", details={"fields": errors})
    return value


class LLMExecutor:
    async def run(self, node: LLMNode, rt: RuntimeContext, state: GraphState, extra: dict[str, Any]) -> Any:
        cfg = node.config
        snap = rt.llm.config_for(node.id)
        context = rt.template_context(state, extra)
        messages: list[Any] = []
        system = system_prompt_for(node, rt, context)
        schema = cfg.output_schema
        use_native_schema = bool(schema) and snap.supports_json_schema
        if schema and not use_native_schema:
            system = ((system or "") + "\n\n" + _JSON_INSTRUCTION.format(schema=json.dumps(schema))).strip()
        if system:
            messages.append(SystemMessage(content=system))
        messages.append(UserMessage(content=render(cfg.user_prompt, context) if cfg.user_prompt else "Continue."))
        budget = ContextBudget(max_input_tokens=max(1000, snap.context_window - (snap.max_tokens or 4096)))
        request = LLMRequest(
            model=snap.model_name,
            messages=fit_messages(messages, [], budget),
            temperature=snap.temperature,
            max_tokens=snap.max_tokens,
            extras=snap.extras,
            response_format=ResponseFormat(json_schema=schema) if use_native_schema and schema else None,
        )
        response = await rt.llm.generate(node.id, request)
        if schema:
            return parse_structured(response.message.content, schema)
        return {"text": response.message.content or "", "model": response.model}


class ToolCallFailed(AppError):
    code = ErrorCode.mcp_tool_error


class MCPToolExecutor:
    async def run(self, node: MCPToolNode, rt: RuntimeContext, state: GraphState, extra: dict[str, Any]) -> Any:
        arguments = resolve(node.config.arguments, rt.names(state, extra))
        if not isinstance(arguments, dict):
            raise AppError("Tool arguments must resolve to an object", code=ErrorCode.tool_arguments_invalid)
        index = int(extra.get("__index__", 0))
        outcome = await rt.tools.route(
            node_id=node.id,
            call_seq=index,
            name=node.config.tool,
            arguments=arguments,
            allowlist=[node.config.tool],
            in_map=node.map is not None,
            context_summary=f"Pipeline step '{node.name}' wants to call {node.config.tool}.",
        )
        if outcome.status == RouteStatus.completed:
            return outcome.structured
        retryable = outcome.status == RouteStatus.failed and outcome.error_code in (
            ErrorCode.mcp_connection_failed,
            ErrorCode.tool_timeout,
        )
        raise ToolCallFailed(
            f"{node.config.tool} {outcome.status.value}: {outcome.content[:300]}",
            code=outcome.error_code or ErrorCode.mcp_tool_error,
            retryable=retryable,
            details={"tool": node.config.tool, "status": outcome.status.value},
        )
