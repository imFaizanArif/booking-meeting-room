"use client";

import { Badge } from "@/components/ui/badge";
import { JsonViewer } from "@/components/ui/json-viewer";
import { Drawer } from "@/components/ui/overlay";
import { DescriptionList } from "@/components/ui/page";
import { dateTime } from "@/lib/format";

import type { Tool } from "./queries";
import { RiskSelect, STALE_REASON, ToolSwitch } from "./tool-controls";

function ControlRow({ htmlFor, label, hint, children }: { htmlFor?: string; label: string; hint: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div>
        <label htmlFor={htmlFor} className="text-xs font-medium">
          {label}
        </label>
        <p className="text-xs text-fg-subtle">{hint}</p>
      </div>
      {children}
    </div>
  );
}

export function ToolDrawer({ tool, onClose, canEdit }: { tool: Tool | null; onClose: () => void; canEdit: boolean }) {
  const annotations = tool?.annotations ?? {};
  return (
    <Drawer
      open={!!tool}
      onOpenChange={(o) => !o && onClose()}
      title={tool ? <span className="font-mono">{tool.name}</span> : "Tool"}
      description={tool ? <span className="font-mono">{tool.namespaced_name}</span> : undefined}
    >
      {tool ? (
        <div className="flex flex-col gap-5">
          {tool.is_stale ? (
            <p role="status" className="rounded-md bg-danger-bg px-3 py-2 text-sm text-danger">
              {STALE_REASON}
            </p>
          ) : null}
          {tool.description ? <p className="whitespace-pre-wrap text-sm text-fg-muted">{tool.description}</p> : null}

          <DescriptionList
            items={[
              { label: "Server", value: tool.server_name },
              ...(tool.title ? [{ label: "Title", value: tool.title }] : []),
              { label: "Read only", value: tool.is_read_only ? "Yes (server hint)" : "No" },
              { label: "Last discovered", value: dateTime(tool.last_discovered_at) },
              { label: "Schema hash", value: <span className="font-mono text-xs">{tool.schema_hash.slice(0, 16)}</span> },
            ]}
          />

          <section className="flex flex-col">
            <h3 className="border-b border-border pb-1.5 text-xs font-semibold text-fg-muted">Policy</h3>
            <div className="flex flex-col divide-y divide-border">
              <ControlRow htmlFor="td-enabled" label="Enabled" hint="Agents can only see and call enabled tools.">
                <ToolSwitch tool={tool} flag="is_enabled" canEdit={canEdit} id="td-enabled" />
              </ControlRow>
              <ControlRow htmlFor="td-approval" label="Requires approval" hint="Each call pauses the execution until someone approves it.">
                <ToolSwitch tool={tool} flag="requires_approval" canEdit={canEdit} id="td-approval" />
              </ControlRow>
              <ControlRow htmlFor="td-destructive" label="Destructive" hint="Calls change or delete data and cannot be undone. Shown to reviewers.">
                <ToolSwitch tool={tool} flag="is_destructive" canEdit={canEdit} id="td-destructive" />
              </ControlRow>
              <ControlRow htmlFor={`td-risk-${tool.id}`} label="Risk level" hint="Shown to reviewers on each approval request.">
                <RiskSelect tool={tool} canEdit={canEdit} idPrefix="td-risk" />
              </ControlRow>
            </div>
          </section>

          <section className="flex flex-col gap-1.5">
            <h3 className="flex items-center gap-2 text-xs font-semibold text-fg-muted">
              Annotations
              <span className="font-normal text-fg-subtle">Hints from the server, not guarantees</span>
            </h3>
            {Object.keys(annotations).length ? (
              <div className="flex flex-wrap gap-1">
                {Object.entries(annotations).map(([k, v]) => (
                  <Badge key={k} tone="outline" className="font-mono">
                    {k}: {typeof v === "object" ? JSON.stringify(v) : String(v)}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-xs text-fg-subtle">The server sent no annotations.</p>
            )}
          </section>

          <section className="flex flex-col gap-1.5">
            <h3 className="text-xs font-semibold text-fg-muted">Input schema</h3>
            <JsonViewer value={tool.input_schema} defaultOpen={3} className="max-h-[360px]" />
          </section>

          {tool.output_schema ? (
            <section className="flex flex-col gap-1.5">
              <h3 className="text-xs font-semibold text-fg-muted">Output schema</h3>
              <JsonViewer value={tool.output_schema} defaultOpen={2} className="max-h-[240px]" />
            </section>
          ) : null}
        </div>
      ) : null}
    </Drawer>
  );
}
