"use client";

import { AlertTriangle, ArrowRight, CircleAlert, ExternalLink, Trash2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { MultiSelect, type MultiSelectOption } from "@/components/ui-extra/multi-select";
import { Badge, Kbd } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldRow } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { type FieldOverride, JsonSchemaForm } from "@/components/ui/json-schema-form";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/toggles";
import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { decorateSchema, issuesToFieldErrors } from "../config-schema";
import {
  type Branch,
  type BuilderAction,
  DEFAULT_ERROR_POLICY,
  type ErrorPolicy,
  type Graph,
  type GraphEdge,
  type GraphNode,
  isFallback,
  MAPPABLE,
  templateCompletions,
} from "../graph";
import type { GraphIssue } from "../mutations";
import { NODE_ICONS } from "../node-meta";
import { JsonCodeField, TemplateField } from "./fields";

type NodeTypeOut = Schemas["NodeTypeOut"];
type Model = Schemas["ModelOut"];
type Tool = Schemas["MCPToolOut"];
type Template = Schemas["PromptTemplateOut"];
type Variable = Schemas["PromptVariableOut"];
type Channel = Schemas["ChannelOut"];

export interface PanelData {
  nodeTypes: Record<string, NodeTypeOut>;
  models: Model[];
  tools: Tool[];
  templates: Template[];
  variables: Variable[];
  channels: Channel[];
}

const DEFAULT = "__default";
const NONE = "__none";
const LATEST = "__latest";

function PanelSection({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3 border-b border-border px-4 py-4 last:border-b-0">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold text-fg">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

function ToolLabel({ tool }: { tool: Tool }) {
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      <span className="truncate font-mono text-xs">{tool.namespaced_name}</span>
      {tool.requires_approval ? <Badge tone="warn">Approval</Badge> : null}
      {tool.is_destructive ? <Badge tone="danger">Destructive</Badge> : null}
    </span>
  );
}

// ---------------------------------------------------------------------------------------

export function NodeConfigPanel({
  node,
  graph,
  dispatch,
  data,
  issues,
  readOnly,
  onDelete,
}: {
  node: GraphNode;
  graph: Graph;
  dispatch: React.Dispatch<BuilderAction>;
  data: PanelData;
  issues: GraphIssue[];
  readOnly?: boolean;
  onDelete: () => void;
}) {
  const typeInfo = data.nodeTypes[node.type];
  const Icon = NODE_ICONS[node.type];
  const schema = React.useMemo(() => decorateSchema(node.type, typeInfo?.config_schema), [node.type, typeInfo]);
  const completions = React.useMemo(
    () => templateCompletions(graph, node.id, data.variables.map((v) => v.key)),
    [graph, node.id, data.variables],
  );
  const fieldErrors = React.useMemo(() => issuesToFieldErrors(issues), [issues]);
  const patch = (p: Parameters<typeof dispatch>[0] extends infer A ? (A extends { type: "updateNode"; patch: infer P } ? P : never) : never) =>
    dispatch({ type: "updateNode", id: node.id, patch: p });

  const activeModels = data.models.filter((m) => m.is_active);
  const enabledTools = data.tools.filter((t) => t.is_enabled && !t.is_stale);

  const override: FieldOverride = ({ path, value, onChange, error }) => {
    const id = `cfg-${path}`;
    switch (path) {
      case "model_id": {
        const current = typeof value === "string" ? value : null;
        const options = [
          { value: DEFAULT, label: "Workspace default", description: activeModels.find((m) => m.is_default)?.display_name },
          ...activeModels.map((m) => ({ value: m.id, label: m.display_name, description: `${m.provider_name} · ${m.model_name}` })),
        ];
        if (current && !activeModels.some((m) => m.id === current)) options.push({ value: current, label: "Unavailable model", description: current });
        return <Select id={id} value={current ?? DEFAULT} onValueChange={(v) => onChange(v === DEFAULT ? null : v)} options={options} aria-invalid={!!error} />;
      }
      case "system_prompt.template_id": {
        const current = typeof value === "string" ? value : null;
        const options = [
          { value: NONE, label: "None, use inline prompt" },
          ...data.templates.map((t) => ({ value: t.id, label: t.name, description: `v${t.latest_version} · ${t.variables?.length ?? 0} variables` })),
        ];
        if (current && !data.templates.some((t) => t.id === current)) options.push({ value: current, label: "Missing template", description: current });
        return (
          <div className="flex flex-col gap-1">
            <Select id={id} value={current ?? NONE} onValueChange={(v) => onChange(v === NONE ? null : v)} options={options} />
            {current ? (
              <Link href={`/prompts?t=${current}`} target="_blank" className="inline-flex items-center gap-1 self-start text-xs text-fg-muted hover:text-fg">
                Open in prompt studio <ExternalLink className="size-3" />
              </Link>
            ) : null}
          </div>
        );
      }
      case "system_prompt.version": {
        const prompt = (node.config.system_prompt ?? {}) as { template_id?: string | null };
        const template = data.templates.find((t) => t.id === prompt.template_id);
        if (!template) return <p className="text-xs text-fg-subtle">Pick a template to pin a version.</p>;
        const options = [
          { value: LATEST, label: `Latest at run time (now v${template.latest_version})` },
          ...Array.from({ length: template.latest_version }, (_, i) => template.latest_version - i).map((v) => ({ value: String(v), label: `v${v}` })),
        ];
        return <Select id={id} value={typeof value === "number" ? String(value) : LATEST} onValueChange={(v) => onChange(v === LATEST ? null : Number(v))} options={options} />;
      }
      case "system_prompt.inline": {
        const prompt = (node.config.system_prompt ?? {}) as { template_id?: string | null };
        if (prompt.template_id) return <p className="text-xs text-fg-subtle">Not used while a template is selected.</p>;
        return <TemplateField ariaLabel="Inline system prompt" value={(value as string) ?? ""} onChange={(v) => onChange(v || null)} completions={completions} invalid={!!error} />;
      }
      case "user_prompt":
      case "message":
      case "instructions":
        return <TemplateField ariaLabel={path.replace("_", " ")} value={(value as string) ?? ""} onChange={onChange} completions={completions} invalid={!!error} minHeight={path === "user_prompt" ? "120px" : "72px"} />;
      case "tool": {
        const current = typeof value === "string" && value ? value : undefined;
        const options = enabledTools.map((t) => ({ value: t.namespaced_name, label: <ToolLabel tool={t} />, description: t.description ?? undefined }));
        if (current && !enabledTools.some((t) => t.namespaced_name === current)) options.push({ value: current, label: <span className="font-mono text-xs text-danger">{current}</span>, description: "Not enabled or not discovered" });
        return <Select id={id} value={current} onValueChange={onChange} options={options} placeholder="Select a tool" aria-invalid={!!error} />;
      }
      case "tool_allowlist": {
        const options: MultiSelectOption[] = enabledTools.map((t) => ({ value: t.namespaced_name, text: t.namespaced_name, label: <ToolLabel tool={t} />, description: t.description ?? undefined }));
        return <MultiSelect id={id} value={Array.isArray(value) ? (value as string[]) : []} onChange={onChange} options={options} placeholder="No tools" emptyText="No enabled tools. Enable tools on the MCP servers page." aria-invalid={!!error} />;
      }
      case "channel_ids": {
        const options: MultiSelectOption[] = data.channels.map((c) => ({ value: c.id, text: c.name, label: c.name, description: c.channel_type, disabled: !c.is_active }));
        return <MultiSelect id={id} value={Array.isArray(value) ? (value as string[]) : []} onChange={onChange} options={options} placeholder="No channels" emptyText="No notification channels. Add one in settings." />;
      }
      case "output_schema":
        return <JsonCodeField ariaLabel="Output schema" value={value} onChange={onChange} nullable invalid={!!error} />;
      case "input_schema":
      case "arguments":
      case "template":
      case "provider_extras":
      case "output":
        return <JsonCodeField ariaLabel={path.replace("_", " ")} value={value} onChange={onChange} nullable={path === "template"} invalid={!!error} />;
      default:
        return undefined;
    }
  };

  const mappable = MAPPABLE.has(node.type);
  const policy: ErrorPolicy = node.error_policy ?? DEFAULT_ERROR_POLICY;
  const nodeIssues = issues.filter((i) => !i.edge_id);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex items-center gap-2 border-b border-border px-4 py-2.5">
        <Icon className="size-4 text-fg-muted" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">{node.name}</p>
          <p className="truncate text-2xs text-fg-subtle">{typeInfo?.label ?? node.type}</p>
        </div>
        {!readOnly ? (
          <Button variant="ghost" size="icon" aria-label="Delete node" onClick={onDelete}>
            <Trash2 />
          </Button>
        ) : null}
      </header>
      <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto">
        {nodeIssues.length ? (
          <ul className="flex flex-col gap-1 border-b border-border bg-subtle px-4 py-3">
            {nodeIssues.map((i, n) => (
              <li key={n} className={cn("flex items-start gap-1.5 text-xs", i.severity === "warning" ? "text-warn" : "text-danger")}>
                {i.severity === "warning" ? <AlertTriangle className="mt-0.5 size-3 shrink-0" /> : <CircleAlert className="mt-0.5 size-3 shrink-0" />}
                <span>{i.message}</span>
              </li>
            ))}
          </ul>
        ) : null}
        <fieldset disabled={readOnly} className="contents">
          <PanelSection title="General">
            <Field label="Name" htmlFor="cfg-name">
              <Input id="cfg-name" value={node.name} maxLength={120} onChange={(e) => patch({ name: e.target.value })} />
            </Field>
            <Field label="Id" htmlFor="cfg-id" hint={<>Fixed after creation. Reference the output as <code className="font-mono">nodes.{node.id}.output</code>.</>}>
              <Input id="cfg-id" value={node.id} readOnly className="font-mono text-xs text-fg-muted" />
            </Field>
            <Field label="Notes" htmlFor="cfg-notes">
              <Textarea id="cfg-notes" rows={2} value={node.notes ?? ""} placeholder="Why this step exists" onChange={(e) => patch({ notes: e.target.value || null })} />
            </Field>
          </PanelSection>

          <PanelSection title="Configuration">
            {typeInfo ? (
              <JsonSchemaForm
                key={node.id}
                idPrefix="cfg-"
                schema={schema}
                value={node.config ?? {}}
                onChange={(config) => patch({ config })}
                errors={fieldErrors}
                override={override}
              />
            ) : (
              <p className="text-xs text-fg-muted">Loading the schema for this node type.</p>
            )}
          </PanelSection>

          {mappable ? (
            <PanelSection
              title="Map"
              aside={
                <Switch
                  aria-label="Run once per item"
                  checked={!!node.map}
                  onCheckedChange={(on) => patch({ map: on ? { over: "", concurrency: 4, item_name: "item" } : null })}
                />
              }
            >
              {node.map ? (
                <>
                  <Field label="Over" htmlFor="cfg-map-over" hint="Expression that evaluates to a list.">
                    <Input
                      id="cfg-map-over"
                      className="font-mono text-xs"
                      value={node.map.over}
                      placeholder="nodes.filter.output.items"
                      onChange={(e) => patch({ map: { ...node.map!, over: e.target.value } })}
                    />
                  </Field>
                  <FieldRow>
                    <Field label="Concurrency" htmlFor="cfg-map-conc">
                      <Input
                        id="cfg-map-conc"
                        type="number"
                        min={1}
                        max={32}
                        value={node.map.concurrency}
                        onChange={(e) => patch({ map: { ...node.map!, concurrency: Math.max(1, Math.min(32, Number(e.target.value) || 1)) } })}
                      />
                    </Field>
                    <Field label="Item name" htmlFor="cfg-map-item">
                      <Input id="cfg-map-item" className="font-mono text-xs" value={node.map.item_name} onChange={(e) => patch({ map: { ...node.map!, item_name: e.target.value } })} />
                    </Field>
                  </FieldRow>
                </>
              ) : (
                <p className="text-xs text-fg-muted">Off. Turn on to run this node once per element of a list.</p>
              )}
            </PanelSection>
          ) : null}

          {node.type !== "trigger" && node.type !== "end" ? (
            <PanelSection title="Error handling">
              <FieldRow>
                <Field label="On error" htmlFor="cfg-ep-mode">
                  <Select
                    id="cfg-ep-mode"
                    size="sm"
                    value={policy.mode}
                    onValueChange={(v) => patch({ error_policy: { ...policy, mode: v as ErrorPolicy["mode"] } })}
                    options={[
                      { value: "retry", label: "Retry" },
                      { value: "fail", label: "Fail the run" },
                      { value: "fallback", label: "Follow error edge" },
                      { value: "pause", label: "Pause for review" },
                    ]}
                  />
                </Field>
                <Field label="Then" htmlFor="cfg-ep-then" hint={policy.mode === "retry" ? "When retries run out" : undefined}>
                  <Select
                    id="cfg-ep-then"
                    size="sm"
                    value={policy.then}
                    onValueChange={(v) => patch({ error_policy: { ...policy, then: v as ErrorPolicy["then"] } })}
                    options={[
                      { value: "fail", label: "Fail the run" },
                      { value: "fallback", label: "Follow error edge" },
                      { value: "pause", label: "Pause for review" },
                    ]}
                  />
                </Field>
              </FieldRow>
              {policy.mode === "retry" ? (
                <FieldRow>
                  <Field label="Max attempts" htmlFor="cfg-ep-max">
                    <Input
                      id="cfg-ep-max"
                      type="number"
                      min={1}
                      max={10}
                      value={policy.max_attempts}
                      onChange={(e) => patch({ error_policy: { ...policy, max_attempts: Math.max(1, Math.min(10, Number(e.target.value) || 1)) } })}
                    />
                  </Field>
                  <Field label="Backoff (seconds)" htmlFor="cfg-ep-backoff">
                    <Input
                      id="cfg-ep-backoff"
                      type="number"
                      min={0}
                      max={300}
                      step={0.5}
                      value={policy.backoff_seconds}
                      onChange={(e) => patch({ error_policy: { ...policy, backoff_seconds: Math.max(0, Math.min(300, Number(e.target.value) || 0)) } })}
                    />
                  </Field>
                </FieldRow>
              ) : null}
              {isFallback(policy) ? (
                <p className="text-xs text-fg-muted">Connect the red handle at the bottom of the node to the step that handles the error.</p>
              ) : null}
            </PanelSection>
          ) : null}
        </fieldset>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------

export function EdgeConfigPanel({ edge, graph, dispatch, readOnly, onDelete }: {
  edge: GraphEdge;
  graph: Graph;
  dispatch: React.Dispatch<BuilderAction>;
  readOnly?: boolean;
  onDelete: () => void;
}) {
  const source = graph.nodes.find((n) => n.id === edge.source);
  const target = graph.nodes.find((n) => n.id === edge.target);
  const isCondition = source?.type === "condition";
  const options = isCondition
    ? [
        { value: "true", label: "True" },
        { value: "false", label: "False" },
        { value: "error", label: "Error (fallback)" },
      ]
    : [
        { value: "none", label: "Always" },
        { value: "error", label: "Error (fallback)" },
      ];
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex items-center gap-2 border-b border-border px-4 py-2.5">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">Edge</p>
          <p className="truncate font-mono text-2xs text-fg-subtle">{edge.id}</p>
        </div>
        {!readOnly ? (
          <Button variant="ghost" size="icon" aria-label="Delete edge" onClick={onDelete}>
            <Trash2 />
          </Button>
        ) : null}
      </header>
      <PanelSection title="Connection">
        <p className="flex flex-wrap items-center gap-1.5 text-sm">
          <span className="font-medium">{source?.name ?? edge.source}</span>
          <ArrowRight className="size-3.5 text-fg-subtle" aria-hidden />
          <span className="font-medium">{target?.name ?? edge.target}</span>
        </p>
        <Field label="Branch" htmlFor="edge-branch" hint={edge.branch === "error" && source && !isFallback(source.error_policy) ? "The source node's error policy does not fall back, so this edge is never taken." : "Which outcome of the source follows this edge."}>
          <Select
            id="edge-branch"
            disabled={readOnly}
            value={edge.branch ?? "none"}
            onValueChange={(v) => dispatch({ type: "edgeBranch", id: edge.id, branch: v === "none" ? null : (v as Branch) })}
            options={options}
          />
        </Field>
      </PanelSection>
    </div>
  );
}

// ---------------------------------------------------------------------------------------

export function OverviewPanel({ description, nodes, edges, multi, onDeleteSelection, readOnly }: {
  description: string | null;
  nodes: number;
  edges: number;
  multi: number;
  onDeleteSelection: () => void;
  readOnly?: boolean;
}) {
  return (
    <div className="scrollbar-thin flex min-h-0 flex-1 flex-col overflow-y-auto">
      {multi > 1 ? (
        <PanelSection title={`${multi} items selected`}>
          <p className="text-xs text-fg-muted">Select a single node or edge to edit it.</p>
          {!readOnly ? (
            <Button variant="danger-outline" size="sm" className="self-start" onClick={onDeleteSelection}>
              <Trash2 /> Delete selected
            </Button>
          ) : null}
        </PanelSection>
      ) : (
        <PanelSection title="Pipeline">
          <p className="text-sm text-fg-muted">{description || "No description."}</p>
          <p className="tabular text-xs text-fg-subtle">
            {nodes} nodes · {edges} edges
          </p>
          <p className="text-xs text-fg-muted">Select a node to configure it, or add one from the palette.</p>
        </PanelSection>
      )}
      <PanelSection title="Shortcuts">
        <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 text-xs">
          <dt className="text-fg-muted">Delete selection</dt>
          <dd><Kbd>⌫</Kbd></dd>
          <dt className="text-fg-muted">Add to selection</dt>
          <dd className="flex gap-1"><Kbd>⇧</Kbd><span className="text-fg-subtle">click</span></dd>
          <dt className="text-fg-muted">Box select</dt>
          <dd className="flex gap-1"><Kbd>⇧</Kbd><span className="text-fg-subtle">drag</span></dd>
          <dt className="text-fg-muted">Save version</dt>
          <dd className="flex gap-1"><Kbd>⌘</Kbd><Kbd>S</Kbd></dd>
        </dl>
      </PanelSection>
    </div>
  );
}
