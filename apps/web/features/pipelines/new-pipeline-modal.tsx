"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Modal } from "@/components/ui/overlay";
import { ApiError } from "@/lib/api/client";

import { useCreatePipeline } from "./mutations";

const schema = z.object({
  name: z.string().trim().min(1, "Give the pipeline a name.").max(200, "Keep the name under 200 characters."),
  description: z.string().trim().max(2000).optional(),
});
type Values = z.infer<typeof schema>;

export function NewPipelineModal({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const router = useRouter();
  const create = useCreatePipeline();
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { name: "", description: "" } });
  const [formError, setFormError] = React.useState<ApiError | null>(null);

  const setOpen = (next: boolean) => {
    if (!next) {
      form.reset();
      setFormError(null);
    }
    onOpenChange(next);
  };

  const submit = form.handleSubmit((values) => {
    setFormError(null);
    create.mutate(
      { name: values.name, description: values.description || null },
      {
        onSuccess: (p) => router.push(`/pipelines/${p.id}`),
        onError: (error) => {
          if (error instanceof ApiError) {
            const fields = error.fields;
            fields.forEach((f) => {
              const key = f.field.split(".").pop();
              if (key === "name" || key === "description") form.setError(key, { message: f.message });
            });
            if (error.status === 409) form.setError("name", { message: error.message });
            else if (!fields.length) setFormError(error);
          }
        },
      },
    );
  });

  return (
    <Modal
      open={open}
      onOpenChange={setOpen}
      title="New pipeline"
      description="Starts with a trigger connected to an end node. You build the rest in the editor."
      footer={
        <>
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="new-pipeline-form" loading={create.isPending}>
            Create and open builder
          </Button>
        </>
      }
    >
      <form id="new-pipeline-form" onSubmit={submit} className="flex flex-col gap-3" noValidate>
        <Field label="Name" htmlFor="np-name" required error={form.formState.errors.name?.message}>
          <Input id="np-name" autoFocus autoComplete="off" placeholder="Weekly report" aria-invalid={!!form.formState.errors.name} {...form.register("name")} />
        </Field>
        <Field label="Description" htmlFor="np-desc" hint="Optional. Shown in the pipeline list." error={form.formState.errors.description?.message}>
          <Textarea id="np-desc" rows={3} {...form.register("description")} />
        </Field>
        {formError ? (
          <p role="alert" className="text-xs text-danger">
            {formError.message}
            {formError.requestId ? <span className="ml-1 font-mono text-fg-muted">request {formError.requestId}</span> : null}
          </p>
        ) : null}
      </form>
    </Modal>
  );
}
