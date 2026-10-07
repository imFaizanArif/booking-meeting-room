"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Braces, Pencil, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { Field, FieldRow } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { ConfirmDialog } from "@/components/ui/overlay";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { applyServerErrors, FormError } from "@/components/ui-extra/form-error";
import { ApiError, type Schemas } from "@/lib/api/client";
import { relativeTime } from "@/lib/format";

import { useDeleteVariable, useSaveVariable } from "./mutations";
import { usePromptVariables } from "./queries";
import { ReadOnlyNote, SettingsSection } from "./section";

type Variable = Schemas["PromptVariableOut"];

export const VARIABLE_KEY_RE = /^[a-z_][a-z0-9_]{0,99}$/;

export const variableSchema = z.object({
  key: z.string().regex(VARIABLE_KEY_RE, "Lowercase letters, digits and underscores; must not start with a digit"),
  value: z.string().max(100_000, "100,000 characters at most"),
  description: z.string().max(500, "500 characters at most"),
});
type VariableValues = z.infer<typeof variableSchema>;

export function VariableEditor({ variable, existingKeys, onDone }: { variable: Variable | null; existingKeys: string[]; onDone: () => void }) {
  const save = useSaveVariable();
  const [error, setError] = React.useState<unknown>(null);
  const form = useForm<VariableValues>({
    resolver: zodResolver(variableSchema),
    defaultValues: { key: variable?.key ?? "", value: variable?.value ?? "", description: variable?.description ?? "" },
  });
  const { errors } = form.formState;

  async function onSubmit(v: VariableValues) {
    setError(null);
    if (!variable && existingKeys.includes(v.key)) {
      form.setError("key", { type: "validate", message: "A variable with this key exists. Edit it instead." });
      return;
    }
    try {
      const saved = await save.mutateAsync({ key: v.key, value: v.value, description: v.description.trim() || null });
      toast.success(`Saved {{ ${saved.key} }}`);
      onDone();
    } catch (err) {
      const leftover = applyServerErrors(err, form.setError, ["key", "value", "description"]);
      if (!(err instanceof ApiError && err.fields.length && !leftover.length)) setError(err);
    }
  }

  return (
    <form
      onSubmit={form.handleSubmit(onSubmit)}
      noValidate
      aria-label={variable ? `Edit variable ${variable.key}` : "New variable"}
      className="flex flex-col gap-3 rounded-md border border-border-strong bg-surface p-4"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onDone();
        }
      }}
    >
      <FieldRow>
        <Field label="Key" htmlFor="v-key" required error={errors.key?.message} hint={variable ? "Keys cannot be renamed." : "Lowercase, digits and underscores."}>
          <Input
            id="v-key"
            className="font-mono"
            autoComplete="off"
            spellCheck={false}
            autoFocus={!variable}
            readOnly={!!variable}
            aria-invalid={!!errors.key}
            placeholder="company_name"
            {...form.register("key")}
          />
        </Field>
        <Field label="Description" htmlFor="v-desc" error={errors.description?.message}>
          <Input id="v-desc" autoComplete="off" placeholder="What it is for" aria-invalid={!!errors.description} {...form.register("description")} />
        </Field>
      </FieldRow>
      <Field label="Value" htmlFor="v-value" error={errors.value?.message} hint="Plain text, inserted as-is. Multiple lines are kept.">
        <Textarea id="v-value" rows={4} autoFocus={!!variable} className="font-mono text-xs" aria-invalid={!!errors.value} {...form.register("value")} />
      </Field>
      <FormError error={error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" loading={save.isPending}>
          Save variable
        </Button>
      </div>
    </form>
  );
}

export function VariablesSection({ canEdit }: { canEdit: boolean }) {
  const variables = usePromptVariables();
  const remove = useDeleteVariable();
  const [editing, setEditing] = React.useState<Variable | "new" | null>(null);
  const [deleting, setDeleting] = React.useState<Variable | null>(null);
  const editorRef = React.useRef<HTMLDivElement>(null);

  function edit(v: Variable | "new") {
    setEditing(v);
    requestAnimationFrame(() => editorRef.current?.scrollIntoView({ block: "nearest" }));
  }

  const keys = variables.data?.map((v) => v.key) ?? [];

  return (
    <SettingsSection
      id="variables"
      title="Prompt variables"
      description={
        <>
          Workspace-wide values every prompt can use as <span className="font-mono text-fg">{"{{ key }}"}</span> (also <span className="font-mono text-fg">{"{{ vars.key }}"}</span>). They are
          stored in plain text and shown to anyone in the workspace, so never put secrets here.
        </>
      }
      actions={
        canEdit && editing === null && variables.data?.length ? (
          <Button size="sm" onClick={() => edit("new")}>
            <Plus /> Add variable
          </Button>
        ) : null
      }
    >
      <div ref={editorRef} className="scroll-mt-6">
        {editing !== null ? (
          <VariableEditor key={editing === "new" ? "new" : editing.key} variable={editing === "new" ? null : editing} existingKeys={keys} onDone={() => setEditing(null)} />
        ) : null}
      </div>
      {variables.isPending ? (
        <LoadingState rows={3} />
      ) : variables.error ? (
        <ErrorState error={variables.error} onRetry={() => void variables.refetch()} />
      ) : variables.data.length === 0 && editing === null ? (
        <EmptyState
          icon={Braces}
          title="No prompt variables"
          body="Define values such as your name, company or tone of voice once and reuse them in every prompt."
          action={
            canEdit ? (
              <Button size="sm" onClick={() => edit("new")}>
                <Plus /> Add variable
              </Button>
            ) : undefined
          }
        />
      ) : variables.data.length ? (
        <DataTable
          rows={variables.data}
          getRowId={(v) => v.key}
          searchText={variables.data.length > 8 ? (v) => `${v.key} ${v.value} ${v.description ?? ""}` : undefined}
          searchPlaceholder="Filter variables"
          rowClassName={(v) => (editing !== null && editing !== "new" && editing.key === v.key ? "bg-subtle" : undefined)}
          columns={[
            { id: "key", header: "Key", sortValue: (v) => v.key, className: "whitespace-nowrap", cell: (v) => <span className="font-mono text-xs font-medium">{v.key}</span> },
            {
              id: "value",
              header: "Value",
              cell: (v) => (
                <span className="line-clamp-2 max-w-[48ch] whitespace-pre-wrap break-words font-mono text-xs text-fg-muted" title={v.value.length > 200 ? `${v.value.slice(0, 200)}…` : v.value}>
                  {v.value || <span className="text-fg-subtle">empty</span>}
                </span>
              ),
            },
            { id: "description", header: "Description", cell: (v) => <span className="text-fg-muted">{v.description || "—"}</span> },
            { id: "updated", header: "Updated", sortValue: (v) => v.updated_at, className: "whitespace-nowrap", cell: (v) => <span className="text-xs text-fg-muted">{relativeTime(v.updated_at)}</span> },
            {
              id: "actions",
              header: <span className="sr-only">Actions</span>,
              align: "right",
              cell: (v) =>
                canEdit ? (
                  <div className="flex justify-end gap-0.5">
                    <Button size="icon" variant="ghost" aria-label={`Edit ${v.key}`} onClick={() => edit(v)}>
                      <Pencil />
                    </Button>
                    <Button size="icon" variant="ghost" aria-label={`Delete ${v.key}`} onClick={() => setDeleting(v)}>
                      <Trash2 />
                    </Button>
                  </div>
                ) : null,
            },
          ]}
        />
      ) : null}
      {!canEdit ? <ReadOnlyNote>Operators and owners can change prompt variables.</ReadOnlyNote> : null}
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="Delete variable"
        tone="danger"
        confirmLabel="Delete variable"
        loading={remove.isPending}
        body={
          <>
            Prompts that use <span className="font-mono text-fg">{`{{ ${deleting?.key ?? ""} }}`}</span> will fail to render until you add it again, unless the run input supplies it.
          </>
        }
        onConfirm={() =>
          deleting &&
          remove.mutate(deleting.key, {
            onSuccess: () => {
              if (editing !== null && editing !== "new" && editing.key === deleting.key) setEditing(null);
              setDeleting(null);
            },
          })
        }
      />
    </SettingsSection>
  );
}
