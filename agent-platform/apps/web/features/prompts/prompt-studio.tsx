"use client";

import { FileText, History, Plus, Search, Trash2 } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Gate } from "@/components/ui-extra/gate";
import { FormError } from "@/components/ui-extra/form-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CodeEditor } from "@/components/ui/code-editor";
import { DiffViewer } from "@/components/ui/diff-viewer";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { ConfirmDialog, Drawer, Modal } from "@/components/ui/overlay";
import { PageHeader, Panel } from "@/components/ui/page";
import { EmptyState, ErrorState, LoadingState, Skeleton } from "@/components/ui/states";
import { canOperate } from "@/features/auth/queries";
import type { Schemas } from "@/lib/api/client";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useAddPromptVersion, useCreatePrompt, useDeletePrompt } from "./mutations";
import { usePromptPreview, usePromptTemplate, usePromptTemplates, usePromptVariables } from "./queries";

type Template = Schemas["PromptTemplateOut"];
type Detail = Schemas["PromptTemplateDetail"];

/** Names the run-time context always provides; anything else must come from workspace variables. */
const RUNTIME_ROOTS = ["input", "nodes", "item", "index", "vars", "execution"];

const DEFAULT_SAMPLE = `{
  "input": {},
  "nodes": {},
  "item": null
}`;

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = React.useState(value);
  React.useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

export function PromptStudio({ role }: { role: string | undefined }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const templates = usePromptTemplates();
  const [query, setQuery] = React.useState("");
  const [creating, setCreating] = React.useState(false);
  const operator = canOperate(role);

  const selectedId = params.get("t") ?? templates.data?.[0]?.id ?? null;
  const select = React.useCallback(
    (id: string) => router.replace(`${pathname}?t=${id}`, { scroll: false }),
    [router, pathname],
  );

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = templates.data ?? [];
    return q ? list.filter((t) => t.name.toLowerCase().includes(q) || (t.description ?? "").toLowerCase().includes(q)) : list;
  }, [templates.data, query]);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Prompts"
        description="Versioned templates for LLM and Agent nodes. Nodes pin a version or follow the latest one at run time."
        actions={
          <Gate allowed={operator} reason="Operators and owners can create templates">
            <Button variant="primary" onClick={() => setCreating(true)}>
              <Plus /> New template
            </Button>
          </Gate>
        }
      />

      {templates.isPending ? (
        <LoadingState rows={6} />
      ) : templates.isError ? (
        <ErrorState error={templates.error} onRetry={() => void templates.refetch()} />
      ) : !templates.data.length ? (
        <EmptyState
          icon={FileText}
          title="No prompt templates yet"
          body="Templates keep system and user prompts out of the pipeline graph so they can be reviewed and versioned on their own."
          action={operator ? <Button variant="primary" onClick={() => setCreating(true)}><Plus /> New template</Button> : undefined}
        />
      ) : (
        <div className="grid min-h-[560px] grid-cols-[248px_minmax(0,1fr)] gap-5">
          <nav aria-label="Templates" className="flex flex-col gap-2">
            <label className="relative">
              <span className="sr-only">Filter templates</span>
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-fg-subtle" />
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter" className="pl-8" />
            </label>
            <ul className="flex flex-col">
              {filtered.map((t) => (
                <li key={t.id}>
                  <button
                    type="button"
                    onClick={() => select(t.id)}
                    aria-current={t.id === selectedId ? "page" : undefined}
                    className={cn(
                      "flex w-full flex-col gap-0.5 rounded-md px-2.5 py-2 text-left transition-colors duration-100",
                      t.id === selectedId ? "bg-subtle text-fg" : "text-fg-muted hover:bg-subtle/60 hover:text-fg",
                    )}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{t.name}</span>
                      <span className="tabular shrink-0 text-2xs text-fg-subtle">v{t.latest_version}</span>
                    </span>
                    <span className="truncate text-xs text-fg-subtle">{t.description || `${t.variables.length} variables`}</span>
                  </button>
                </li>
              ))}
              {!filtered.length ? <li className="px-2.5 py-2 text-xs text-fg-subtle">No match for “{query}”.</li> : null}
            </ul>
          </nav>
          {selectedId ? <TemplateEditor key={selectedId} id={selectedId} operator={operator} onDeleted={() => router.replace(pathname)} /> : null}
        </div>
      )}

      <CreateTemplateModal open={creating} onOpenChange={setCreating} onCreated={(t) => select(t.id)} />
    </div>
  );
}

function TemplateEditor({ id, operator, onDeleted }: { id: string; operator: boolean; onDeleted: () => void }) {
  const detail = usePromptTemplate(id);
  if (detail.isPending) return <Skeleton className="h-[560px]" />;
  if (detail.isError) return <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />;
  return <TemplateEditorLoaded key={detail.data.latest_version} template={detail.data} operator={operator} onDeleted={onDeleted} />;
}

function TemplateEditorLoaded({ template, operator, onDeleted }: { template: Detail; operator: boolean; onDeleted: () => void }) {
  const variables = usePromptVariables();
  const [body, setBody] = React.useState(template.latest_body);
  const [sample, setSample] = React.useState(DEFAULT_SAMPLE);
  const [saving, setSaving] = React.useState(false);
  const [historyOpen, setHistoryOpen] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);
  const remove = useDeletePrompt();

  const dirty = body !== template.latest_body;
  const debouncedBody = useDebounced(body, 300);
  const debouncedSample = useDebounced(sample, 300);
  const preview = usePromptPreview(debouncedBody, debouncedSample);
  const sampleInvalid = React.useMemo(() => {
    try {
      const v: unknown = JSON.parse(sample || "{}");
      return !v || typeof v !== "object" || Array.isArray(v);
    } catch {
      return true;
    }
  }, [sample]);

  const workspaceKeys = React.useMemo(() => (variables.data ?? []).map((v) => v.key), [variables.data]);
  const completions = React.useMemo(
    () => [...RUNTIME_ROOTS.map((r) => (r === "vars" ? "vars." : r)), ...workspaceKeys.map((k) => `vars.${k}`), ...workspaceKeys],
    [workspaceKeys],
  );
  const referenced = preview.data?.variables ?? template.variables;
  const unresolved = new Set(preview.data?.unresolved ?? []);

  React.useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (dirty && operator) setSaving(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [dirty, operator]);

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-base font-semibold">{template.name}</h2>
            <Badge tone="outline">v{template.latest_version}</Badge>
            {dirty ? <Badge tone="warn">Unsaved draft</Badge> : null}
          </div>
          <p className="mt-0.5 text-xs text-fg-muted">
            {template.description ? `${template.description} · ` : ""}Updated {relativeTime(template.updated_at)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={() => setHistoryOpen(true)}>
            <History /> History
          </Button>
          {dirty ? (
            <Button variant="ghost" onClick={() => setBody(template.latest_body)}>
              Discard
            </Button>
          ) : null}
          <Gate allowed={operator} reason="Operators and owners can edit templates">
            <Button variant="primary" disabled={!dirty} onClick={() => setSaving(true)}>
              Save as v{template.latest_version + 1}
            </Button>
          </Gate>
          <Gate allowed={operator} reason="Operators and owners can delete templates">
            <Button variant="ghost" size="icon" aria-label="Delete template" onClick={() => setDeleting(true)}>
              <Trash2 />
            </Button>
          </Gate>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)]">
        <div className="flex min-w-0 flex-col gap-2">
          <div className="flex items-baseline justify-between">
            <span className="text-xs font-medium text-fg-muted">Template</span>
            <span className="text-2xs text-fg-subtle">
              Jinja syntax. Type <code className="font-mono">{"{{"}</code> for variables.
            </span>
          </div>
          <CodeEditor
            value={body}
            onChange={setBody}
            language="template"
            readOnly={!operator}
            minHeight="360px"
            maxHeight="560px"
            completions={completions}
            ariaLabel="Template body"
            invalid={!!preview.data?.error}
          />
          {preview.data?.error ? <p className="text-xs text-danger">{preview.data.error}</p> : null}

          <div className="mt-2 flex flex-col gap-1.5">
            <span className="text-xs font-medium text-fg-muted">Variables</span>
            {referenced.length ? (
              <ul className="flex flex-col divide-y divide-border rounded-md border border-border">
                {referenced.map((name) => (
                  <VariableRow key={name} name={name} unresolved={unresolved.has(name)} workspaceKeys={workspaceKeys} />
                ))}
              </ul>
            ) : (
              <p className="text-xs text-fg-subtle">This template references no variables.</p>
            )}
          </div>
        </div>

        <div className="flex min-w-0 flex-col gap-2">
          <span className="text-xs font-medium text-fg-muted">Sample context</span>
          <CodeEditor value={sample} onChange={setSample} language="json" minHeight="120px" maxHeight="220px" ariaLabel="Sample context JSON" invalid={sampleInvalid} />
          {sampleInvalid ? <p className="text-xs text-danger">Sample must be a JSON object.</p> : null}

          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-xs font-medium text-fg-muted">Preview</span>
            {preview.isFetching ? <span className="text-2xs text-fg-subtle">Rendering…</span> : null}
          </div>
          <Panel className="min-h-[200px] overflow-auto bg-subtle/40 px-3 py-2.5">
            {preview.isError ? (
              <FormError error={preview.error} />
            ) : preview.data?.rendered != null ? (
              <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">{preview.data.rendered || " "}</pre>
            ) : (
              <p className="text-xs text-fg-subtle">{preview.data?.error ? "Fix the template error to see a preview." : "Nothing to render yet."}</p>
            )}
          </Panel>
          {unresolved.size ? (
            <p className="text-xs text-warn">
              {unresolved.size} variable{unresolved.size === 1 ? "" : "s"} rendered empty. Add {unresolved.size === 1 ? "it" : "them"} to the sample, or define a workspace variable in Settings.
            </p>
          ) : null}
        </div>
      </div>

      <SaveVersionModal open={saving} onOpenChange={setSaving} template={template} body={body} />
      <HistoryDrawer open={historyOpen} onOpenChange={setHistoryOpen} template={template} draft={body} onLoad={(b) => { setBody(b); setHistoryOpen(false); }} />
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete ${template.name}?`}
        body="Nodes that reference this template will fail validation until they point at another template. Past executions keep the rendered prompt they used."
        confirmLabel="Delete template"
        tone="danger"
        loading={remove.isPending}
        onConfirm={() =>
          remove.mutate(template.id, {
            onSuccess: () => {
              toast.success(`Deleted ${template.name}`);
              setDeleting(false);
              onDeleted();
            },
          })
        }
      />
    </div>
  );
}

function VariableRow({ name, unresolved, workspaceKeys }: { name: string; unresolved: boolean; workspaceKeys: string[] }) {
  const root = name.split(".")[0] ?? name;
  const source = RUNTIME_ROOTS.includes(root)
    ? root === "vars"
      ? "workspace variable"
      : "run time"
    : workspaceKeys.includes(root)
      ? "workspace variable"
      : "undefined";
  return (
    <li className="flex items-center justify-between gap-3 px-3 py-1.5">
      <code className="truncate font-mono text-xs">{name}</code>
      <span className="flex shrink-0 items-center gap-1.5">
        {unresolved ? <Badge tone="warn">empty in preview</Badge> : null}
        <Badge tone={source === "undefined" ? "danger" : source === "run time" ? "info" : "neutral"}>{source}</Badge>
      </span>
    </li>
  );
}

function CreateTemplateModal({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (o: boolean) => void; onCreated: (t: Template) => void }) {
  const create = useCreatePrompt();
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");

  const [wasOpen, setWasOpen] = React.useState(open);
  if (wasOpen !== open) {
    setWasOpen(open);
    if (open) {
      setName("");
      setDescription("");
    }
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    create.mutate(
      { name: name.trim(), description: description.trim() || null, body: "", change_note: "Created" },
      {
        onSuccess: (t) => {
          toast.success(`Created ${t.name}`);
          onOpenChange(false);
          onCreated(t);
        },
      },
    );
  };

  return (
    <Modal
      open={open}
      onOpenChange={(o) => {
        if (!o) create.reset();
        onOpenChange(o);
      }}
      title="New prompt template"
      description="Starts empty at v1. Write the body in the editor, then save it as a new version."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" type="submit" form="create-template" loading={create.isPending} disabled={!name.trim()}>
            Create template
          </Button>
        </>
      }
    >
      <form id="create-template" onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Name" htmlFor="tpl-name" required>
          <Input id="tpl-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus maxLength={200} placeholder="Proposal writer" />
        </Field>
        <Field label="Description" htmlFor="tpl-desc" hint="Shown in the template picker on LLM and Agent nodes.">
          <Input id="tpl-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <FormError error={create.error} />
      </form>
    </Modal>
  );
}

function SaveVersionModal({ open, onOpenChange, template, body }: { open: boolean; onOpenChange: (o: boolean) => void; template: Detail; body: string }) {
  const save = useAddPromptVersion(template.id);
  const [note, setNote] = React.useState("");

  const [wasOpen, setWasOpen] = React.useState(open);
  if (wasOpen !== open) {
    setWasOpen(open);
    if (open) setNote("");
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    save.mutate(
      { body, change_note: note.trim() || null },
      {
        onSuccess: (t) => {
          toast.success(`Saved ${t.name} v${t.latest_version}`);
          onOpenChange(false);
        },
      },
    );
  };

  return (
    <Modal
      open={open}
      onOpenChange={(o) => {
        if (!o) save.reset();
        onOpenChange(o);
      }}
      title={`Save ${template.name} v${template.latest_version + 1}`}
      description="Nodes following the latest version pick this up on their next run. Pinned nodes keep their version."
      className="max-w-2xl"
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" type="submit" form="save-version" loading={save.isPending}>Save version</Button>
        </>
      }
    >
      <form id="save-version" onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Change note" htmlFor="tpl-note" hint="What changed and why. Shown in the version history.">
          <Textarea id="tpl-note" value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={500} autoFocus />
        </Field>
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-fg-muted">Changes from v{template.latest_version}</span>
          <DiffViewer before={template.latest_body} after={body} className="max-h-[280px] overflow-auto" />
        </div>
        <FormError error={save.error} />
      </form>
    </Modal>
  );
}

function HistoryDrawer({
  open,
  onOpenChange,
  template,
  draft,
  onLoad,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  template: Detail;
  draft: string;
  onLoad: (body: string) => void;
}) {
  const versions = React.useMemo(() => [...template.versions].sort((a, b) => b.version - a.version), [template.versions]);
  const [selected, setSelected] = React.useState<number | null>(null);
  const current = versions.find((v) => v.version === selected) ?? versions[0];

  return (
    <Drawer open={open} onOpenChange={onOpenChange} title="Version history" description="Compare any version with the current draft." className="max-w-2xl">
      <div className="flex flex-col gap-4">
        <ul className="flex flex-col divide-y divide-border rounded-md border border-border">
          {versions.map((v) => (
            <li key={v.id}>
              <button
                type="button"
                onClick={() => setSelected(v.version)}
                aria-pressed={current?.version === v.version}
                className={cn("flex w-full items-start gap-3 px-3 py-2 text-left transition-colors duration-100 hover:bg-subtle/60", current?.version === v.version && "bg-subtle")}
              >
                <span className="tabular w-8 shrink-0 text-sm font-medium">v{v.version}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm">{v.change_note || <span className="text-fg-subtle">No change note</span>}</span>
                  <span className="text-2xs text-fg-subtle">{relativeTime(v.created_at)}</span>
                </span>
                {v.version === template.latest_version ? <Badge tone="info">latest</Badge> : null}
              </button>
            </li>
          ))}
        </ul>
        {current ? (
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-fg-muted">v{current.version} → draft</span>
              <Button size="sm" onClick={() => onLoad(current.body)} disabled={current.body === draft}>
                Load v{current.version} into the editor
              </Button>
            </div>
            {current.body === draft ? (
              <p className="text-xs text-fg-subtle">The draft matches v{current.version}.</p>
            ) : (
              <DiffViewer before={current.body} after={draft} />
            )}
          </div>
        ) : null}
      </div>
    </Drawer>
  );
}
