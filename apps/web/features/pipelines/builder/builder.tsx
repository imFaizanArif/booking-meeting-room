"use client";

import { ReactFlowProvider } from "@xyflow/react";
import { ArrowLeft, CheckCircle2, History, Play, Save, ShieldCheck, TriangleAlert } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/overlay";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { canOperate, useMe } from "@/features/auth/queries";
import { usePromptTemplates, usePromptVariables } from "@/features/prompts/queries";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import {
  type Branch,
  type Graph,
  type NodeType,
  type Position,
  connect,
  createNode,
  graphReducer,
  initialState,
  isDirty,
  suggestPosition,
  toGraph,
  triggerInputDefaults,
} from "../graph";
import { type GraphIssue, issuesFromError, useSaveVersion, useUpdatePipeline, useValidateGraph } from "../mutations";
import { nodeSummary } from "../node-meta";
import { useChannels, useModels, useNodeTypes, usePipeline, useTools } from "../queries";
import { BuilderCanvas, type Selection } from "./canvas";
import { EdgeConfigPanel, NodeConfigPanel, OverviewPanel, type PanelData } from "./config-panel";
import { HistoryDrawer } from "./history-drawer";
import { NodePalette } from "./palette";
import { RunModal } from "./run-modal";

const EMPTY: Selection = { nodes: [], edges: [] };

function NameField({ name, onSave, readOnly }: { name: string; onSave: (name: string) => void; readOnly?: boolean }) {
  const [editing, setEditing] = React.useState(false);
  const [value, setValue] = React.useState(name);
  const [prevName, setPrevName] = React.useState(name);
  if (prevName !== name) {
    setPrevName(name);
    setValue(name);
  }
  if (!editing || readOnly) {
    return (
      <button
        type="button"
        disabled={readOnly}
        onClick={() => setEditing(true)}
        className="truncate rounded-sm px-1 text-left text-base font-semibold hover:bg-subtle disabled:hover:bg-transparent"
        title={readOnly ? undefined : "Rename"}
      >
        {name}
      </button>
    );
  }
  const commit = () => {
    setEditing(false);
    const next = value.trim();
    if (next && next !== name) onSave(next);
    else setValue(name);
  };
  return (
    <Input
      autoFocus
      aria-label="Pipeline name"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
        if (e.key === "Escape") {
          setValue(name);
          setEditing(false);
        }
      }}
      className="h-7 w-72 text-base font-semibold"
    />
  );
}

export function PipelineBuilder({ id }: { id: string }) {
  const me = useMe();
  const pipeline = usePipeline(id);
  const nodeTypes = useNodeTypes();
  const models = useModels();
  const tools = useTools();
  const templates = usePromptTemplates();
  const variables = usePromptVariables();
  const channels = useChannels();
  const save = useSaveVersion(id);
  const rename = useUpdatePipeline(id);
  const validate = useValidateGraph();

  const [state, dispatch] = React.useReducer(graphReducer, null, () => initialState(null));
  const [loadedVersion, setLoadedVersion] = React.useState<string | null>(null);
  const [selection, setSelection] = React.useState<Selection>(EMPTY);
  const [issues, setIssues] = React.useState<GraphIssue[] | null>(null);
  const [dialog, setDialog] = React.useState<null | "save" | "run" | "history">(null);
  const [note, setNote] = React.useState("");
  const [restoredFrom, setRestoredFrom] = React.useState<number | null>(null);

  const latest = pipeline.data?.latest;
  if (latest && latest.id !== loadedVersion) {
    // Adjusting state while rendering: load each newly saved version exactly once.
    dispatch({ type: "load", graph: toGraph(latest.graph) });
    setLoadedVersion(latest.id);
    setRestoredFrom(null);
  }

  const dirty = isDirty(state.saved, state.graph);
  React.useEffect(() => {
    if (!dirty) return;
    const onUnload = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", onUnload);
    return () => window.removeEventListener("beforeunload", onUnload);
  }, [dirty]);

  const readOnly = !canOperate(me.data?.role);
  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key.toLowerCase() === "s" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        if (dirty && !readOnly) setDialog("save");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dirty, readOnly]);
  const typeMap = React.useMemo(() => Object.fromEntries((nodeTypes.data ?? []).map((t) => [t.type, t])), [nodeTypes.data]);
  const panelData: PanelData = {
    nodeTypes: typeMap,
    models: models.data ?? [],
    tools: tools.data ?? [],
    templates: templates.data ?? [],
    variables: variables.data ?? [],
    channels: channels.data ?? [],
  };
  const summaries = React.useMemo(() => {
    const modelName = (mid: string) => models.data?.find((m) => m.id === mid)?.display_name;
    const templateName = (tid: string) => templates.data?.find((t) => t.id === tid)?.name;
    return Object.fromEntries(state.graph.nodes.map((n) => [n.id, nodeSummary(n, { modelName, templateName })]));
  }, [state.graph.nodes, models.data, templates.data]);
  const issueMap = React.useMemo(() => {
    const out: Record<string, "error" | "warning"> = {};
    for (const issue of issues ?? []) {
      if (!issue.node_id) continue;
      if (issue.severity === "error" || !out[issue.node_id]) out[issue.node_id] = issue.severity === "error" ? "error" : "warning";
    }
    return out;
  }, [issues]);

  const addNode = React.useCallback(
    (type: NodeType, position?: Position) => {
      const info = typeMap[type];
      const anchor = selection.nodes.length === 1 ? selection.nodes[0] : null;
      const node = createNode({
        type,
        label: info?.label ?? type,
        configSchema: info?.config_schema,
        position: position ?? suggestPosition(state.graph, anchor),
        graph: state.graph,
      });
      dispatch({ type: "addNode", node, connectFrom: position ? null : anchor });
      setSelection({ nodes: [node.id], edges: [] });
    },
    [typeMap, selection.nodes, state.graph],
  );

  const validateConnection = React.useCallback(
    (source: string, target: string, branch: Branch | null) => {
      const result = connect(state.graph, source, target, branch);
      return result.ok ? null : result.reason;
    },
    [state.graph],
  );

  async function runValidation() {
    try {
      const result = await validate.mutateAsync(state.graph);
      setIssues(result.issues);
      if (result.ok) toast.success(result.issues.length ? "Valid, with warnings." : "The pipeline is valid.");
      else toast.error("The pipeline has errors. They are highlighted on the canvas.");
    } catch {
      /* toast from the mutation cache */
    }
  }

  async function saveVersion() {
    try {
      const detail = await save.mutateAsync({ graph: state.graph, change_note: note.trim() || (restoredFrom ? `Restored from v${restoredFrom}` : null) });
      dispatch({ type: "saved", graph: state.graph });
      setLoadedVersion(detail.latest?.id ?? null);
      setIssues(null);
      setNote("");
      setRestoredFrom(null);
      setDialog(null);
      toast.success(`Saved as version ${detail.latest_version_number}.`);
    } catch (e) {
      const found = issuesFromError(e);
      if (found.length) {
        setIssues(found);
        setDialog(null);
        toast.error("Fix the highlighted problems before saving.");
      } else if (e instanceof ApiError) {
        toast.error(e.message);
      }
    }
  }

  if (pipeline.isPending || nodeTypes.isPending) {
    return (
      <div className="p-8">
        <LoadingState rows={8} />
      </div>
    );
  }
  if (pipeline.error) return <ErrorState error={pipeline.error} onRetry={() => void pipeline.refetch()} className="m-8" />;

  const detail = pipeline.data;
  const selectedNode = selection.nodes.length === 1 && selection.edges.length === 0 ? state.graph.nodes.find((n) => n.id === selection.nodes[0]) : undefined;
  const selectedEdge = selection.edges.length === 1 && selection.nodes.length === 0 ? state.graph.edges.find((e) => e.id === selection.edges[0]) : undefined;
  const errorCount = (issues ?? []).filter((i) => i.severity === "error").length;
  const removeSelection = () => {
    dispatch({ type: "remove", nodeIds: selection.nodes, edgeIds: selection.edges });
    setSelection(EMPTY);
  };

  return (
    <div className="flex h-dvh min-h-0 flex-col">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border bg-surface px-4">
        <Link href="/pipelines" className="text-fg-muted hover:text-fg" aria-label="Back to pipelines">
          <ArrowLeft className="size-4" />
        </Link>
        <NameField name={detail.name} readOnly={readOnly} onSave={(name) => rename.mutate({ name }, { onSuccess: () => toast.success("Renamed.") })} />
        <Badge tone="outline" className="font-mono">v{detail.latest_version_number}</Badge>
        {dirty ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-warn">
            <span className="size-1.5 rounded-full bg-warn" aria-hidden />
            Unsaved changes{restoredFrom ? ` (loaded from v${restoredFrom})` : ""}
          </span>
        ) : (
          <span className="text-xs text-fg-subtle">Saved</span>
        )}
        {readOnly ? <Badge>Read-only</Badge> : null}
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={() => setDialog("history")}>
            <History /> History
          </Button>
          <Button size="sm" variant="ghost" onClick={() => void runValidation()} loading={validate.isPending}>
            <ShieldCheck /> Validate
          </Button>
          {!readOnly ? (
            <Button size="sm" onClick={() => setDialog("save")} disabled={!dirty}>
              <Save /> Save version
            </Button>
          ) : null}
          {!readOnly ? (
            <Button size="sm" variant="primary" onClick={() => setDialog("run")}>
              <Play /> Run
            </Button>
          ) : null}
        </div>
      </header>

      {issues && issues.length ? (
        <div className={cn("flex max-h-28 shrink-0 flex-col overflow-y-auto border-b border-border px-4 py-2 text-xs", errorCount ? "bg-danger-bg" : "bg-warn-bg")}>
          <div className="mb-1 flex items-center justify-between">
            <span className={cn("inline-flex items-center gap-1.5 font-medium", errorCount ? "text-danger" : "text-warn")}>
              <TriangleAlert className="size-3.5" />
              {errorCount ? `${errorCount} error${errorCount > 1 ? "s" : ""}` : "Warnings only"}
            </span>
            <button type="button" className="text-fg-muted hover:text-fg" onClick={() => setIssues(null)}>Dismiss</button>
          </div>
          <ul className="flex flex-col gap-0.5">
            {issues.map((issue, i) => (
              <li key={i}>
                <button
                  type="button"
                  disabled={!issue.node_id}
                  onClick={() => issue.node_id && setSelection({ nodes: [issue.node_id], edges: [] })}
                  className={cn("text-left hover:underline disabled:no-underline", issue.severity === "error" ? "text-danger" : "text-warn")}
                >
                  {issue.node_id ? <span className="font-mono">{issue.node_id}: </span> : null}
                  {issue.message}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : issues ? (
        <div className="flex shrink-0 items-center gap-1.5 border-b border-border bg-ok-bg px-4 py-1.5 text-xs text-ok">
          <CheckCircle2 className="size-3.5" /> No problems found.
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1">
        <NodePalette nodeTypes={typeMap} onAdd={(t) => addNode(t)} disabled={readOnly} />
        <div className="relative min-w-0 flex-1">
          <ReactFlowProvider>
            <BuilderCanvas
              graph={state.graph}
              selection={selection}
              onSelectionChange={setSelection}
              dispatch={dispatch}
              summaries={summaries}
              issues={issueMap}
              readOnly={readOnly}
              showMinimap={state.graph.nodes.length > 12}
              onDropType={(type, position) => addNode(type, position)}
              onConnectRejected={(reason) => toast.error(reason)}
              validateConnection={validateConnection}
            />
          </ReactFlowProvider>
        </div>
        <aside className="scrollbar-thin w-[340px] shrink-0 overflow-y-auto border-l border-border bg-surface" aria-label="Inspector">
          {selectedNode ? (
            <NodeConfigPanel
              key={selectedNode.id}
              node={selectedNode}
              graph={state.graph}
              dispatch={dispatch}
              data={panelData}
              issues={(issues ?? []).filter((i) => i.node_id === selectedNode.id)}
              readOnly={readOnly}
              onDelete={removeSelection}
            />
          ) : selectedEdge ? (
            <EdgeConfigPanel edge={selectedEdge} graph={state.graph} dispatch={dispatch} readOnly={readOnly} onDelete={removeSelection} />
          ) : (
            <OverviewPanel
              description={detail.description ?? null}
              nodes={state.graph.nodes.length}
              edges={state.graph.edges.length}
              multi={selection.nodes.length + selection.edges.length}
              onDeleteSelection={removeSelection}
              readOnly={readOnly}
            />
          )}
        </aside>
      </div>

      <Modal
        open={dialog === "save"}
        onOpenChange={(o) => setDialog(o ? "save" : null)}
        title={`Save as version ${detail.latest_version_number + 1}`}
        description="Versions are immutable. Running and scheduled executions keep using the version they started with."
        footer={
          <>
            <Button variant="ghost" onClick={() => setDialog(null)}>Cancel</Button>
            <Button variant="primary" onClick={() => void saveVersion()} loading={save.isPending}>Save version</Button>
          </>
        }
      >
        <Field label="Change note" htmlFor="change-note" hint="Optional. Shown in the version history.">
          <Input
            id="change-note"
            autoFocus
            value={note}
            maxLength={500}
            placeholder={restoredFrom ? `Restored from v${restoredFrom}` : "What changed?"}
            onChange={(e) => setNote(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void saveVersion()}
          />
        </Field>
      </Modal>

      <RunModal
        open={dialog === "run"}
        onOpenChange={(o) => setDialog(o ? "run" : null)}
        pipelineId={id}
        defaults={triggerInputDefaults(state.saved ?? state.graph)}
        dirty={dirty}
        version={detail.latest_version_number}
      />

      <HistoryDrawer
        open={dialog === "history"}
        onOpenChange={(o) => setDialog(o ? "history" : null)}
        pipelineId={id}
        versions={detail.versions}
        latest={detail.latest_version_number}
        onRestore={(graph: Graph, version: number) => {
          dispatch({ type: "restore", graph });
          setRestoredFrom(version);
          setSelection(EMPTY);
          toast.message(`Loaded v${version}. Save to make it the latest version.`);
        }}
      />
    </div>
  );
}
