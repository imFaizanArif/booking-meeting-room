/**
 * Presentation tweaks for node config schemas served by GET /node-types: friendlier titles,
 * a sensible field order and a few hints. Pure; the schema itself still drives the form.
 */

import type { JsonSchema } from "@/components/ui/json-schema-form";

import type { GraphIssue } from "./mutations";
import type { NodeType } from "./graph";

const TITLES: Record<string, string> = {
  model_id: "Model",
  system_prompt: "System prompt",
  template_id: "Template",
  version: "Template version",
  inline: "Inline system prompt",
  user_prompt: "User prompt",
  output_schema: "Output schema",
  provider_extras: "Provider extras",
  tool_allowlist: "Allowed tools",
  tool: "Tool",
  input_schema: "Input schema",
  allow_manual: "Allow manual runs",
  allow_schedule: "Allow schedules",
  allow_webhook: "Allow webhook calls",
  channel_ids: "Channels",
  expires_in_minutes: "Expires after (minutes)",
  allow_edit: "Reviewer can edit data",
  on_reject: "When a tool call is rejected",
  token_budget: "Token budget",
  max_tool_calls: "Max tool calls",
  jsonpath: "JSONPath",
};

const DESCRIPTIONS: Record<string, string> = {
  arguments: "Values starting with = are expressions (=input.query); anything else is a literal.",
  template: "Object whose values are =expressions or literals.",
  output: "An =expression, or an object of =expressions and literals.",
  input_schema: "JSON Schema for the run input. Defaults prefill the run dialog.",
  model_id: "Leave on the workspace default to follow it when it changes.",
  user_prompt: "Template. Type {{ to insert input, nodes.<id>.output, vars or item.",
  message: "Template. Type {{ to insert input, nodes.<id>.output or vars.",
  instructions: "Template shown to the reviewer.",
  tool_allowlist: "The agent can only call these tools.",
};

const ORDER: Partial<Record<NodeType, string[]>> = {
  llm: ["model_id", "system_prompt", "user_prompt", "output_schema", "temperature", "max_tokens", "provider_extras"],
  agent: [
    "model_id",
    "system_prompt",
    "user_prompt",
    "tool_allowlist",
    "tool_choice",
    "max_iterations",
    "max_tool_calls",
    "token_budget",
    "on_reject",
    "output_schema",
    "temperature",
    "max_tokens",
    "provider_extras",
  ],
};

function decorateProps(props: Record<string, JsonSchema> | undefined, order?: string[]): Record<string, JsonSchema> | undefined {
  if (!props) return props;
  const keys = Object.keys(props);
  const sorted = order ? [...order.filter((k) => keys.includes(k)), ...keys.filter((k) => !order.includes(k))] : keys;
  const out: Record<string, JsonSchema> = {};
  for (const key of sorted) {
    const prop = { ...props[key]! };
    if (TITLES[key]) prop.title = TITLES[key];
    if (DESCRIPTIONS[key]) prop.description = DESCRIPTIONS[key];
    out[key] = prop;
  }
  return out;
}

export function decorateSchema(type: NodeType, schema: unknown): JsonSchema {
  const s = (schema ?? {}) as JsonSchema;
  const defs = s.$defs
    ? Object.fromEntries(Object.entries(s.$defs).map(([k, d]) => [k, { ...d, properties: decorateProps(d.properties) }]))
    : undefined;
  return { ...s, $defs: defs, properties: decorateProps(s.properties, ORDER[type]) };
}

/**
 * Map server issues for one node onto config field paths. Validation messages look like
 * `expression: …` or `user_prompt: …`; parse errors like `nodes.3.config.tool: Field required`.
 */
export function issuesToFieldErrors(issues: GraphIssue[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const issue of issues) {
    const m = /^(?:nodes\.\d+\.config\.)?([a-z_][a-z0-9_.]*):\s*(.+)$/i.exec(issue.message);
    if (!m) continue;
    const path = m[1]!.replace(/\.\d+/g, "");
    if (path.startsWith("nodes.") || path.startsWith("map")) continue;
    out[path] ??= m[2]!;
  }
  return out;
}
