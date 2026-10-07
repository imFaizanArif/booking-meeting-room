"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { KeyRound, Plus, RotateCw, Trash2 } from "lucide-react";
import * as React from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Tooltip } from "@/components/ui/menus";
import { ConfirmDialog, Modal } from "@/components/ui/overlay";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { CopyText } from "@/components/ui-extra/copy-text";
import { applyServerErrors, FormError } from "@/components/ui-extra/form-error";
import { ApiError, type Schemas } from "@/lib/api/client";
import { dateTime, relativeTime } from "@/lib/format";

import { maskHint } from "./format";
import { useDeleteSecret, usePutSecret } from "./mutations";
import { useSecrets } from "./queries";
import { ReadOnlyNote, SettingsSection } from "./section";

type Secret = Schemas["SecretOut"];

export const SECRET_NAME_RE = /^[A-Za-z0-9_.:-]{1,200}$/;

export const secretSchema = z.object({
  name: z.string().regex(SECRET_NAME_RE, "Letters, digits and _ . : - only, up to 200 characters"),
  value: z.string().min(1, "Enter the secret value").max(20_000, "20,000 characters at most"),
  description: z.string().max(500, "500 characters at most"),
});
type SecretValues = z.infer<typeof secretSchema>;

function SecretForm({ rotating, existingNames, put, onDone }: { rotating: Secret | null; existingNames: string[]; put: ReturnType<typeof usePutSecret>; onDone: () => void }) {
  const [error, setError] = React.useState<unknown>(null);
  const form = useForm<SecretValues>({
    resolver: zodResolver(secretSchema),
    defaultValues: { name: rotating?.name ?? "", value: "", description: rotating?.description ?? "" },
  });
  const { errors } = form.formState;

  async function onSubmit(v: SecretValues) {
    setError(null);
    if (!rotating && existingNames.includes(v.name)) {
      form.setError("name", { type: "validate", message: "A secret with this name exists. Rotate it instead." });
      return;
    }
    try {
      const saved = await put.mutateAsync({ name: v.name, value: v.value, description: v.description.trim() || null });
      form.reset({ name: "", value: "", description: "" });
      toast.success(rotating ? `Rotated ${saved.name} to version ${saved.version}` : `Stored ${saved.name}`);
      onDone();
    } catch (err) {
      const leftover = applyServerErrors(err, form.setError, ["name", "value", "description"]);
      if (!(err instanceof ApiError && err.fields.length && !leftover.length)) setError(err);
    }
  }

  return (
    <form id="secret-form" onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex flex-col gap-3">
      <Field label="Name" htmlFor="sec-name" required error={errors.name?.message} hint={rotating ? undefined : "Letters, digits and _ . : -"}>
        <Input id="sec-name" className="font-mono" autoComplete="off" spellCheck={false} autoFocus={!rotating} readOnly={!!rotating} aria-invalid={!!errors.name} placeholder="GITHUB_TOKEN" {...form.register("name")} />
      </Field>
      <Field label={rotating ? "New value" : "Value"} htmlFor="sec-value" required error={errors.value?.message} hint="Encrypted at rest. It is never shown again, only its last four characters.">
        <Input id="sec-value" type="password" className="font-mono" autoComplete="new-password" spellCheck={false} autoFocus={!!rotating} aria-invalid={!!errors.value} {...form.register("value")} />
      </Field>
      <Field label="Description" htmlFor="sec-desc" error={errors.description?.message}>
        <Input id="sec-desc" autoComplete="off" placeholder="Where it is used" aria-invalid={!!errors.description} {...form.register("description")} />
      </Field>
      <FormError error={error} />
    </form>
  );
}

function SecretModal({ open, onOpenChange, rotating, existingNames }: { open: boolean; onOpenChange: (open: boolean) => void; rotating: Secret | null; existingNames: string[] }) {
  const put = usePutSecret();
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={rotating ? "Rotate secret" : "Add secret"}
      description={rotating ? `Replaces the value of ${rotating.name}. Everything that references it picks up the new value on its next use.` : "Store a credential once and reference it from MCP servers, providers and tools."}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" form="secret-form" variant="primary" loading={put.isPending}>
            {rotating ? "Rotate secret" : "Add secret"}
          </Button>
        </>
      }
    >
      {open ? <SecretForm key={rotating?.id ?? "new"} rotating={rotating} existingNames={existingNames} put={put} onDone={() => onOpenChange(false)} /> : null}
    </Modal>
  );
}

const MANAGED_REASON = "Managed by the configuration field that owns it. Change it there.";

export function SecretsSection({ isOwner }: { isOwner: boolean }) {
  const secrets = useSecrets(isOwner);
  const remove = useDeleteSecret();
  const [modalOpen, setModalOpen] = React.useState(false);
  const [rotating, setRotating] = React.useState<Secret | null>(null);
  const [deleting, setDeleting] = React.useState<Secret | null>(null);

  function openAdd() {
    setRotating(null);
    setModalOpen(true);
  }

  const addButton = (
    <Button size="sm" onClick={openAdd}>
      <Plus /> Add secret
    </Button>
  );

  return (
    <SettingsSection
      id="secrets"
      title="Secrets"
      description="Write-only credentials, encrypted at rest. Values are never returned by the API; only a hint of the last characters is kept."
      actions={isOwner && secrets.data?.length ? addButton : null}
    >
      {!isOwner ? (
        <ReadOnlyNote>Only owners can see and manage secrets.</ReadOnlyNote>
      ) : secrets.isPending ? (
        <LoadingState rows={3} />
      ) : secrets.error ? (
        <ErrorState error={secrets.error} onRetry={() => void secrets.refetch()} />
      ) : secrets.data.length === 0 ? (
        <EmptyState icon={KeyRound} title="No secrets stored" body="API keys and tokens for providers, MCP servers and channels are stored here, encrypted." action={addButton} />
      ) : (
        <DataTable
          rows={secrets.data}
          getRowId={(s) => s.id}
          searchText={secrets.data.length > 8 ? (s) => `${s.name} ${s.description ?? ""}` : undefined}
          searchPlaceholder="Filter secrets"
          columns={[
            {
              id: "name",
              header: "Name",
              sortValue: (s) => s.name,
              cell: (s) => (
                <div className="flex min-w-0 flex-col">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="truncate font-mono text-xs font-medium">{s.name}</span>
                    {s.managed ? (
                      <Tooltip content={MANAGED_REASON}>
                        <span>
                          <Badge tone="outline">Managed</Badge>
                        </span>
                      </Tooltip>
                    ) : null}
                  </span>
                  {s.description ? <span className="truncate text-xs text-fg-muted">{s.description}</span> : null}
                </div>
              ),
            },
            { id: "hint", header: "Value", cell: (s) => <span className="font-mono text-xs text-fg-muted">{maskHint(s.hint)}</span> },
            { id: "ref", header: "Reference", cell: (s) => <CopyText value={s.ref} label="Reference" /> },
            { id: "version", header: "Version", align: "right", sortValue: (s) => s.version, cell: (s) => <span>v{s.version}</span> },
            {
              id: "updated",
              header: "Updated",
              sortValue: (s) => s.updated_at,
              className: "whitespace-nowrap",
              cell: (s) => (
                <span className="text-xs text-fg-muted" title={dateTime(s.updated_at)}>
                  {relativeTime(s.updated_at)}
                </span>
              ),
            },
            {
              id: "actions",
              header: <span className="sr-only">Actions</span>,
              align: "right",
              cell: (s) =>
                s.managed ? (
                  <span className="text-2xs text-fg-subtle">Edit from its owner</span>
                ) : (
                  <div className="flex justify-end gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Rotate ${s.name}`}
                      onClick={() => {
                        setRotating(s);
                        setModalOpen(true);
                      }}
                    >
                      <RotateCw /> Rotate
                    </Button>
                    <Button size="icon" variant="ghost" aria-label={`Delete ${s.name}`} onClick={() => setDeleting(s)}>
                      <Trash2 />
                    </Button>
                  </div>
                ),
            },
          ]}
        />
      )}
      {isOwner ? <SecretModal open={modalOpen} onOpenChange={setModalOpen} rotating={rotating} existingNames={secrets.data?.map((s) => s.name) ?? []} /> : null}
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="Delete secret"
        tone="danger"
        confirmLabel="Delete secret"
        loading={remove.isPending}
        body={
          <div className="flex flex-col gap-2">
            <p>
              <span className="font-mono text-fg">{deleting?.name}</span> is deleted permanently. Anything that references{" "}
              <span className="font-mono text-fg">{deleting?.ref}</span> (a provider key, MCP server env or header) breaks until it is given a new secret.
            </p>
          </div>
        }
        onConfirm={() =>
          deleting &&
          remove.mutate(deleting.id, {
            onSuccess: () => {
              toast.success(`Deleted ${deleting.name}`);
              setDeleting(null);
            },
          })
        }
      />
    </SettingsSection>
  );
}
