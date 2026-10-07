"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import * as React from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { DescriptionList } from "@/components/ui/page";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { applyServerErrors, FormError } from "@/components/ui-extra/form-error";
import { ApiError, type Schemas } from "@/lib/api/client";

import { useUpdateWorkspace } from "./mutations";
import { useWorkspace } from "./queries";
import { ReadOnlyNote, SettingsSection } from "./section";

const schema = z.object({ name: z.string().trim().min(1, "Enter a workspace name").max(200, "200 characters at most") });
type Values = z.infer<typeof schema>;

function NameForm({ workspace }: { workspace: Schemas["WorkspaceOut"] }) {
  const update = useUpdateWorkspace();
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { name: workspace.name } });
  const [error, setError] = React.useState<unknown>(null);

  async function onSubmit(values: Values) {
    setError(null);
    try {
      const saved = await update.mutateAsync({ name: values.name.trim() });
      form.reset({ name: saved.name });
      toast.success("Workspace name saved");
    } catch (err) {
      const leftover = applyServerErrors(err, form.setError, ["name"]);
      if (!(err instanceof ApiError && err.fields.length && !leftover.length)) setError(err);
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex max-w-md flex-col gap-3">
      <Field label="Name" htmlFor="ws-name" error={form.formState.errors.name?.message} hint="Shown in the sidebar and in notifications.">
        <div className="flex gap-2">
          <Input id="ws-name" autoComplete="off" aria-invalid={!!form.formState.errors.name} {...form.register("name")} />
          <Button type="submit" variant="primary" loading={update.isPending} disabled={!form.formState.isDirty}>
            Save name
          </Button>
        </div>
      </Field>
      <DescriptionList items={[{ label: "Slug", value: <span className="font-mono text-xs">{workspace.slug}</span> }]} />
      <FormError error={error} />
    </form>
  );
}

export function WorkspaceSection({ isOwner }: { isOwner: boolean }) {
  const ws = useWorkspace();
  return (
    <SettingsSection id="workspace" title="Workspace" description="The name everyone in this workspace sees.">
      {ws.isPending ? (
        <LoadingState rows={2} />
      ) : ws.error ? (
        <ErrorState error={ws.error} onRetry={() => void ws.refetch()} />
      ) : isOwner ? (
        <NameForm key={ws.data.id} workspace={ws.data} />
      ) : (
        <div className="flex flex-col gap-3">
          <DescriptionList
            items={[
              { label: "Name", value: ws.data.name },
              { label: "Slug", value: <span className="font-mono text-xs">{ws.data.slug}</span> },
            ]}
          />
          <ReadOnlyNote>Only owners can rename the workspace.</ReadOnlyNote>
        </div>
      )}
    </SettingsSection>
  );
}
