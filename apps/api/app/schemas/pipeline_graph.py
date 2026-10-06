"""Pipeline graph: typed nodes, per-type config schemas and edges.

These models are the contract for the builder UI (exported via OpenAPI) and for the
compiler. A node's `config` schema is also served by `GET /node-types` to drive
schema-based forms.

Values in argument maps and output templates follow one convention: a string starting with
`=` is an expression (`=nodes.search.output.jobs`); anything else is a literal.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import NodeType


class Position(BaseModel):
    x: float = 0
    y: float = 0


class MapConfig(BaseModel):
    """Run the node once per element of a list (fan-out inside the node)."""

    over: str = Field(description="Expression that evaluates to a list, e.g. nodes.filter.output.shortlist")
    concurrency: int = Field(default=4, ge=1, le=32)
    item_name: str = Field(default="item", pattern=r"^[a-z_][a-z0-9_]*$")


class ErrorMode(StrEnum):
    fail = "fail"
    retry = "retry"
    fallback = "fallback"
    pause = "pause"


class ErrorPolicy(BaseModel):
    mode: ErrorMode = ErrorMode.retry
    max_attempts: int = Field(default=3, ge=1, le=10)
    backoff_seconds: float = Field(default=1.0, ge=0, le=300)
    then: Literal["fail", "fallback", "pause"] = Field(
        default="fail", description="What happens when retries are exhausted or the error is not retryable"
    )


class ModelSelection(BaseModel):
    model_id: uuid.UUID | None = Field(default=None, description="llm_models.id; null uses the workspace default")
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=128_000)
    provider_extras: dict[str, Any] = Field(
        default_factory=dict, description="Namespaced by provider type, e.g. {\"anthropic\": {...}}"
    )


class PromptRef(BaseModel):
    template_id: uuid.UUID | None = None
    version: int | None = Field(default=None, description="Pinned version; null takes the latest at run time")
    inline: str | None = Field(default=None, description="Used when no template is referenced")


class TriggerConfig(BaseModel):
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    allow_manual: bool = True
    allow_schedule: bool = True
    allow_webhook: bool = False


class LLMConfig(ModelSelection):
    system_prompt: PromptRef = Field(default_factory=PromptRef)
    user_prompt: str = Field(default="", description="Template; may reference input, nodes, vars, item")
    output_schema: dict[str, Any] | None = Field(default=None, description="JSON Schema for structured output")


class OnReject(StrEnum):
    continue_ = "continue"
    end = "end"


class AgentConfig(ModelSelection):
    system_prompt: PromptRef = Field(default_factory=PromptRef)
    user_prompt: str = ""
    tool_allowlist: list[str] = Field(default_factory=list, description="Namespaced tool names: server__tool")
    max_iterations: int = Field(default=8, ge=1, le=50)
    max_tool_calls: int = Field(default=16, ge=0, le=200)
    token_budget: int = Field(default=60_000, ge=1_000, le=2_000_000)
    tool_choice: Literal["auto", "required", "none"] = "auto"
    on_reject: OnReject = OnReject.continue_
    output_schema: dict[str, Any] | None = None


class MCPToolConfig(BaseModel):
    tool: str = Field(description="Namespaced tool name: server__tool")
    arguments: dict[str, Any] = Field(default_factory=dict)


class ConditionConfig(BaseModel):
    expression: str = Field(description="Boolean expression; true/false edges route on it")


class TransformMode(StrEnum):
    expression = "expression"
    jsonpath = "jsonpath"
    template = "template"


class TransformConfig(BaseModel):
    mode: TransformMode = TransformMode.expression
    expression: str | None = None
    source: str | None = Field(default=None, description="jsonpath mode: expression for the document")
    jsonpath: str | None = None
    template: dict[str, Any] | None = Field(default=None, description="template mode: object of =expressions")


class HumanApprovalConfig(BaseModel):
    title: str = "Review required"
    instructions: str = ""
    data: str = Field(default="=input", description="Expression for the data under review")
    allow_edit: bool = True
    expires_in_minutes: int | None = Field(default=None, ge=1)


class NotificationConfig(BaseModel):
    channel_ids: list[uuid.UUID] = Field(default_factory=list)
    message: str = Field(default="", description="Template")


class DelayConfig(BaseModel):
    seconds: int | None = Field(default=None, ge=0, le=60 * 60 * 24 * 30)
    until: str | None = Field(default=None, description="Expression producing an ISO datetime")


class EndConfig(BaseModel):
    output: dict[str, Any] | str = Field(default="=nodes", description="Expression or object template")


class _NodeBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    name: str = Field(min_length=1, max_length=120)
    position: Position = Field(default_factory=Position)
    map: MapConfig | None = None
    error_policy: ErrorPolicy = Field(default_factory=ErrorPolicy)
    notes: str | None = None


class TriggerNode(_NodeBase):
    type: Literal[NodeType.trigger] = NodeType.trigger
    config: TriggerConfig = Field(default_factory=TriggerConfig)


class LLMNode(_NodeBase):
    type: Literal[NodeType.llm] = NodeType.llm
    config: LLMConfig = Field(default_factory=LLMConfig)


class AgentNode(_NodeBase):
    type: Literal[NodeType.agent] = NodeType.agent
    config: AgentConfig = Field(default_factory=AgentConfig)


class MCPToolNode(_NodeBase):
    type: Literal[NodeType.mcp_tool] = NodeType.mcp_tool
    config: MCPToolConfig


class ConditionNode(_NodeBase):
    type: Literal[NodeType.condition] = NodeType.condition
    config: ConditionConfig


class TransformNode(_NodeBase):
    type: Literal[NodeType.transform] = NodeType.transform
    config: TransformConfig = Field(default_factory=TransformConfig)


class HumanApprovalNode(_NodeBase):
    type: Literal[NodeType.human_approval] = NodeType.human_approval
    config: HumanApprovalConfig = Field(default_factory=HumanApprovalConfig)


class NotificationNode(_NodeBase):
    type: Literal[NodeType.notification] = NodeType.notification
    config: NotificationConfig = Field(default_factory=NotificationConfig)


class DelayNode(_NodeBase):
    type: Literal[NodeType.delay] = NodeType.delay
    config: DelayConfig = Field(default_factory=DelayConfig)


class EndNode(_NodeBase):
    type: Literal[NodeType.end] = NodeType.end
    config: EndConfig = Field(default_factory=EndConfig)


PipelineNode = Annotated[
    TriggerNode | LLMNode | AgentNode | MCPToolNode | ConditionNode | TransformNode
    | HumanApprovalNode | NotificationNode | DelayNode | EndNode,
    Field(discriminator="type"),
]

NODE_CONFIG_MODELS: dict[NodeType, type[BaseModel]] = {
    NodeType.trigger: TriggerConfig,
    NodeType.llm: LLMConfig,
    NodeType.agent: AgentConfig,
    NodeType.mcp_tool: MCPToolConfig,
    NodeType.condition: ConditionConfig,
    NodeType.transform: TransformConfig,
    NodeType.human_approval: HumanApprovalConfig,
    NodeType.notification: NotificationConfig,
    NodeType.delay: DelayConfig,
    NodeType.end: EndConfig,
}

MAPPABLE = frozenset({NodeType.llm, NodeType.mcp_tool, NodeType.transform, NodeType.notification})


class EdgeBranch(StrEnum):
    true = "true"
    false = "false"
    error = "error"


class PipelineEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    target: str
    branch: EdgeBranch | None = Field(
        default=None, description="Condition source: true/false. Any source: error (fallback route)"
    )


class PipelineGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[PipelineNode] = Field(default_factory=list)
    edges: list[PipelineEdge] = Field(default_factory=list)

    def node(self, node_id: str) -> PipelineNode:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(node_id)
