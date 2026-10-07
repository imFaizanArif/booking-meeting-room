"use client";

import { ArrowUpRight, Check, Pencil, RotateCcw, ShieldAlert, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CodeEditor } from "@/components/ui/code-editor";
import { DiffViewer } from "@/components/ui/diff-viewer";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { JsonViewer } from "@/components/ui/json-viewer";
import { Modal } from "@/components/ui/overlay";
import { DescriptionList, Section } from "@/components/ui/page";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { RiskBadge, StatusIndicator } from "@/components/ui/status";
import { Checkbox } from "@/components/ui/toggles";
import { canOperate, useMe } from "@/features/auth/queries";
import { ApiError, type Schemas } from "@/lib/api/client";
import { dateTime, relativeTime, shortId } from "@/lib/format";

import { KIND_LABEL } from "./approval-list";
import { useApproval, useDecide } from "./queries";
import { checkArguments, parseArguments } from "./validate";

type Detail = Schemas["ApprovalDetail"];
type Decision = Schemas["DecisionIn"];

function pretty(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

export function ApprovalDetail({ id }: { id: string }) {
  const { data, isPending, error, refetch } = useApproval(id);
  if (isPending) return <LoadingState rows={10} className="p-6" />;
  if (error) return <ErrorState error={error} onRetry={() => void refetch()} className="m-6" />;
  return <DetailBody key={`${data.id}:${data.status}`} approval={data} />;
}

function DetailBody({ approval }: { approval: Detail }) {
  const me = useMe();
  const decide = useDecide(approval.id);
  const operator = canOperate(me.data?.role);
  const pending = approval.status === "pending";
  const isTool = approval.kind === "tool_call";
  const original = isTool ? approval.original_arguments ?? {} : (approval.payload as { data?: unknown } | null)?.data ?? {};
  const allowEdit = isTool || Boolean((approval.payload as { allow_edit?: boolean } | null)?.allow_edit);
  const canRegenerate = isTool && Boolean((approval.payload as { can_regenerate?: boolean } | null)?.can_regenerate);

  const [editing, setEditing] = React.useState(false);
  const [text, setText] = React.useState(() => pretty(original));
  const [serverFields, setServerFields] = React.useState<{ field: string; message: string }[]>([]);
  const [dialog, setDialog] = React.useState<null | "reject" | "regenerate" | "succeeded" | "rerun">(null);

  const parsed = React.useMemo(() => (isTool ? parseArguments(text) : (() => {
    try {
      return { value: JSON.parse(text) as Record<string, unknown> };
    } catch (e) {
      return { error: e instanceof Error ? e.message : "Invalid JSON" };
    }
  })()), [text, isTool]);
  const localIssues = parsed.value && isTool ? checkArguments(approval.input_schema as never, parsed.value) : [];
  const edited = editing && parsed.value !== undefined && pretty(parsed.value) !== pretty(original);

  async function submit(body: Decision, success: string) {
    setServerFields([]);
    try {
      await decide.mutateAsync(body);
      toast.success(success);
      setDialog(null);
      setEditing(false);
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.code === "APPROVAL_ALREADY_DECIDED") {
          toast.error("Someone already decided this approval. Showing the latest state.");
        } else {
          setServerFields(e.fields);
          toast.error(e.message, { description: e.requestId ? `Request ${e.requestId}` : undefined });
        }
      }
    }
  }

  function approve() {
    if (edited && parsed.value) {
      void submit(isTool ? { action: "edit", edited_arguments: parsed.value } : { action: "edit", edited_data: parsed.value }, "Approved with your edits. The execution is resuming.");
    } else {
      void submit({ action: "approve" }, "Approved. The execution is resuming.");
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto">
        <div className="flex flex-col gap-6 px-6 py-5">
          <header className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <StatusIndicator kind="approval" value={approval.status} />
              <span className="text-fg-subtle" aria-hidden>·</span>
              <Badge tone={approval.kind === "outcome_unknown" ? "warn" : "neutral"}>{KIND_LABEL[approval.kind]}</Badge>
              {approval.risk_level ? <RiskBadge level={approval.risk_level} /> : null}
              {(approval.payload as { is_destructive?: boolean } | null)?.is_destructive ? <Badge tone="danger">Destructive</Badge> : null}
            </div>
            <h1 className="font-mono text-lg font-medium">{approval.tool_name ? `${approval.server_slug}.${approval.tool_name}` : approval.title}</h1>
            <DescriptionList
              className="text-xs"
              items={[
                { label: "Pipeline", value: approval.pipeline_name },
                {
                  label: "Execution",
                  value: (
                    <Link href={`/executions/${approval.execution_id}`} className="inline-flex items-center gap-1 font-mono hover:underline">
                      {shortId(approval.execution_id)} <ArrowUpRight className="size-3" />
                    </Link>
                  ),
                },
                { label: "Step", value: <span className="font-mono">{approval.node_id}</span> },
                { label: "Requested", value: `${dateTime(approval.created_at)} (${relativeTime(approval.created_at)})` },
                ...(approval.expires_at ? [{ label: "Expires", value: dateTime(approval.expires_at) }] : []),
              ]}
            />
          </header>

          {approval.reasons.length ? (
            <div className="flex items-start gap-2 rounded-md bg-warn-bg px-3 py-2 text-sm text-warn">
              <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
              <div>
                <p className="font-medium">Why this needs a decision</p>
                <ul className="mt-0.5 list-disc pl-4 text-xs">
                  {approval.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : null}

          {approval.summary ? (
            <Section title={isTool ? "What the agent said" : "Instructions"}>
              <p className="max-w-[72ch] whitespace-pre-wrap text-sm text-fg-muted">{approval.summary}</p>
            </Section>
          ) : null}

          {approval.context.length ? (
            <Section title="Earlier steps in this node" description="Tool calls the agent made before proposing this action.">
              <ol className="flex flex-col divide-y divide-border rounded-md border border-border bg-surface">
                {approval.context.map((step, i) => (
                  <li key={i} className="flex flex-col gap-1 px-3 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs">{String(step.tool)}</span>
                      <StatusIndicator kind="toolCall" value={String(step.status)} />
                    </div>
                    <p className="truncate font-mono text-2xs text-fg-muted">{JSON.stringify(step.arguments)}</p>
                    {step.result_preview ? <p className="line-clamp-2 text-xs text-fg-subtle">{String(step.result_preview)}</p> : null}
                  </li>
                ))}
              </ol>
            </Section>
          ) : null}

          <Section
            title={isTool ? "Proposed arguments" : approval.kind === "outcome_unknown" ? "Arguments of the interrupted call" : "Data under review"}
            description={
              editing
                ? "Edit the JSON. It is validated against the tool's input schema before anything runs."
                : approval.tool_call
                  ? `Idempotency key ${approval.tool_call.idempotency_key}`
                  : undefined
            }
            actions={
              pending && allowEdit && operator && approval.kind !== "outcome_unknown" ? (
                editing ? (
                  <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setText(pretty(original)); setServerFields([]); }}>
                    <RotateCcw /> Discard edits
                  </Button>
                ) : (
                  <Button size="sm" onClick={() => setEditing(true)}>
                    <Pencil /> Edit
                  </Button>
                )
              ) : null
            }
          >
            {editing ? (
              <div className="flex flex-col gap-2">
                <CodeEditor value={text} onChange={setText} ariaLabel="Edited arguments" minHeight="180px" invalid={!!parsed.error || localIssues.length > 0} />
                {parsed.error ? <p className="text-xs text-danger">JSON error: {parsed.error}</p> : null}
                {[...localIssues, ...serverFields].length ? (
                  <ul className="flex flex-col gap-0.5 text-xs text-danger" role="alert">
                    {[...localIssues, ...serverFields].map((issue) => (
                      <li key={`${issue.field}:${issue.message}`}>
                        <span className="font-mono">{issue.field || "(root)"}</span>: {issue.message}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {edited && parsed.value ? (
                  <div className="flex flex-col gap-1">
                    <p className="text-xs font-medium text-fg-muted">Your changes</p>
                    <DiffViewer before={original} after={parsed.value} />
                  </div>
                ) : null}
              </div>
            ) : approval.edited_arguments ? (
              <div className="flex flex-col gap-1">
                <p className="text-xs text-fg-muted">Edited by the reviewer before execution:</p>
                <DiffViewer before={approval.original_arguments} after={approval.edited_arguments} />
              </div>
            ) : (
              <JsonViewer value={original} defaultOpen={3} />
            )}
          </Section>

          {!pending ? <DecisionSummary approval={approval} /> : null}

          {approval.tool_call?.result ? (
            <Section title="Result">
              <JsonViewer value={approval.tool_call.result} defaultOpen={1} />
            </Section>
          ) : null}

          {approval.history.length ? (
            <Section title="Earlier proposals" description="Superseded by a regenerate request.">
              <ul className="flex flex-col divide-y divide-border rounded-md border border-border bg-surface">
                {approval.history.map((h) => (
                  <li key={h.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                    <Link href={`/approvals/${h.id}?filter=all`} className="font-mono text-xs hover:underline">
                      {shortId(h.id)}
                    </Link>
                    <span className="truncate text-xs text-fg-muted">{h.feedback ? `Feedback: ${h.feedback}` : "No feedback"}</span>
                    <StatusIndicator kind="approval" value={h.status} />
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}
        </div>
      </div>

      {pending ? (
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-surface px-6 py-3">
          {!operator ? (
            <p className="text-xs text-fg-muted">You can view this approval. Deciding needs the operator role.</p>
          ) : approval.kind === "outcome_unknown" ? (
            <>
              <p className="max-w-md text-xs text-fg-muted">Check the target system first. This call will not run again unless you choose Re-run.</p>
              <div className="flex gap-2">
                <Button variant="danger-outline" onClick={() => setDialog("rerun")}>Re-run call</Button>
                <Button onClick={() => void submit({ action: "mark_failed" }, "Marked as failed.")} loading={decide.isPending}>
                  Mark failed
                </Button>
                <Button variant="primary" onClick={() => setDialog("succeeded")}>Mark succeeded</Button>
              </div>
            </>
          ) : (
            <>
              <div className="flex gap-2">
                <Button variant="danger-outline" onClick={() => setDialog("reject")}>
                  <X /> Reject
                </Button>
                {canRegenerate ? (
                  <Button variant="ghost" onClick={() => setDialog("regenerate")}>
                    <RotateCcw /> Ask for a new proposal
                  </Button>
                ) : null}
              </div>
              <Button
                variant="primary"
                onClick={approve}
                loading={decide.isPending && !dialog}
                disabled={editing && (!!parsed.error || localIssues.length > 0)}
              >
                <Check /> {edited ? "Approve with edits and execute" : isTool ? "Approve and execute" : "Approve"}
              </Button>
            </>
          )}
        </footer>
      ) : null}

      <ReasonDialog
        open={dialog === "reject"}
        onOpenChange={(o) => setDialog(o ? "reject" : null)}
        title="Reject this action"
        label="Reason"
        hint="The agent receives this reason as the tool result, so it can adjust or stop."
        confirmLabel="Reject action"
        tone="danger"
        required
        loading={decide.isPending}
        onConfirm={(reason) => void submit({ action: "reject", reason }, "Rejected. The agent will be told why.")}
      />
      <ReasonDialog
        open={dialog === "regenerate"}
        onOpenChange={(o) => setDialog(o ? "regenerate" : null)}
        title="Ask for a new proposal"
        label="Feedback for the agent"
        hint="This proposal is kept for the record and marked superseded. The agent proposes again with your feedback."
        confirmLabel="Request new proposal"
        loading={decide.isPending}
        onConfirm={(feedback) => void submit({ action: "regenerate", feedback }, "Sent back for a new proposal.")}
      />
      <SucceededDialog
        open={dialog === "succeeded"}
        onOpenChange={(o) => setDialog(o ? "succeeded" : null)}
        loading={decide.isPending}
        onConfirm={(result) => void submit({ action: "mark_succeeded", result }, "Marked as succeeded.")}
      />
      <RerunDialog
        open={dialog === "rerun"}
        onOpenChange={(o) => setDialog(o ? "rerun" : null)}
        loading={decide.isPending}
        onConfirm={() => void submit({ action: "rerun", confirm: true }, "The call will run once more.")}
      />
    </div>
  );
}

function DecisionSummary({ approval }: { approval: Detail }) {
  return (
    <Section title="Decision">
      <DescriptionList
        items={[
          { label: "Outcome", value: <StatusIndicator kind="approval" value={approval.status} /> },
          { label: "Action", value: approval.decision ?? "—" },
          { label: "Decided by", value: approval.decided_by_email ?? (approval.status === "expired" ? "Expired automatically" : "—") },
          { label: "When", value: dateTime(approval.decided_at) },
          ...(approval.reason ? [{ label: "Reason", value: approval.reason }] : []),
          ...(approval.feedback ? [{ label: "Feedback", value: approval.feedback }] : []),
        ]}
      />
    </Section>
  );
}

function ReasonDialog({ open, onOpenChange, title, label, hint, confirmLabel, tone, required, loading, onConfirm }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  label: string;
  hint: string;
  confirmLabel: string;
  tone?: "danger";
  required?: boolean;
  loading?: boolean;
  onConfirm: (text: string) => void;
}) {
  const [text, setText] = React.useState("");
  const missing = required && !text.trim();
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} loading={loading} disabled={missing} onClick={() => onConfirm(text.trim())}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <Field label={label} htmlFor="decision-text" hint={hint} required={required}>
        <Textarea id="decision-text" autoFocus rows={4} value={text} onChange={(e) => setText(e.target.value)} />
      </Field>
    </Modal>
  );
}

function SucceededDialog({ open, onOpenChange, loading, onConfirm }: { open: boolean; onOpenChange: (o: boolean) => void; loading?: boolean; onConfirm: (result: unknown) => void }) {
  const [text, setText] = React.useState("{}");
  let parsed: unknown;
  let invalid = false;
  try {
    parsed = JSON.parse(text);
  } catch {
    invalid = true;
  }
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title="Mark the call as succeeded"
      description="Record what the target system shows. The agent continues as if the call returned this."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" loading={loading} disabled={invalid} onClick={() => onConfirm(parsed)}>Mark succeeded</Button>
        </>
      }
    >
      <Field label="Observed result (JSON, optional)" htmlFor="observed">
        <CodeEditor value={text} onChange={setText} minHeight="120px" ariaLabel="Observed result" invalid={invalid} />
      </Field>
    </Modal>
  );
}

function RerunDialog({ open, onOpenChange, loading, onConfirm }: { open: boolean; onOpenChange: (o: boolean) => void; loading?: boolean; onConfirm: () => void }) {
  const [checked, setChecked] = React.useState(false);
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title="Run this call again"
      description="The earlier attempt may already have taken effect. Running it again can duplicate the action."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="danger" loading={loading} disabled={!checked} onClick={onConfirm}>Re-run call</Button>
        </>
      }
    >
      <label className="flex items-start gap-2 text-sm">
        <Checkbox checked={checked} onCheckedChange={(c) => setChecked(c === true)} className="mt-0.5" />
        I checked the target system and the action did not happen.
      </label>
    </Modal>
  );
}
