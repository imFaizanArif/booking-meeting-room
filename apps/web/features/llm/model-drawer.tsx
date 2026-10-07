"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import * as React from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { CodeEditor } from "@/components/ui/code-editor";
import { Field, FieldRow } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Drawer } from "@/components/ui/overlay";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/toggles";
import { applyServerErrors } from "@/components/ui-extra/form-errors";

import { useCreateModel, useUpdateModel } from "./mutations";
import { providerTypeLabel, type Model, type Provider } from "./queries";

const price = z
  .string()
  .trim()
  .refine((v) => /^\d+(\.\d{1,6})?$/.test(v), "Enter a price like 3 or 0.25 (up to 6 decimals)");

const schema = z.object({
  provider_id: z.string().min(1, "Choose a provider"),
  display_name: z.string().trim().min(1, "Enter a display name").max(200),
  model_name: z.string().trim().min(1, "Enter the model name the provider expects").max(200),
  context_window: z
    .string()
    .trim()
    .refine((v) => /^\d+$/.test(v) && Number(v) >= 512 && Number(v) <= 10_000_000, "Enter a whole number from 512 to 10,000,000"),
  supports_tools: z.boolean(),
  supports_streaming: z.boolean(),
  supports_json_schema: z.boolean(),
  input_price_per_mtok: price,
  output_price_per_mtok: price,
  default_parameters: z.string().superRefine((v, ctx) => {
    if (v.trim() === "") return;
    try {
      const parsed: unknown = JSON.parse(v);
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        ctx.addIssue({ code: "custom", message: "Default parameters must be a JSON object, like {\"temperature\": 0.2}" });
      }
    } catch (err) {
      ctx.addIssue({ code: "custom", message: `Invalid JSON: ${(err as Error).message}` });
    }
  }),
  is_active: z.boolean(),
});
export type ModelFormValues = z.infer<typeof schema>;

const FIELDS = [
  "provider_id",
  "display_name",
  "model_name",
  "context_window",
  "input_price_per_mtok",
  "output_price_per_mtok",
  "default_parameters",
] as const;

/** "4.000000" -> "4", "0.250000" -> "0.25" */
function trimDecimal(v: string | undefined): string {
  if (!v) return "0";
  return v.includes(".") ? v.replace(/0+$/, "").replace(/\.$/, "") : v;
}

function defaults(m: Model | null, providers: Provider[]): ModelFormValues {
  return {
    provider_id: m?.provider_id ?? providers[0]?.id ?? "",
    display_name: m?.display_name ?? "",
    model_name: m?.model_name ?? "",
    context_window: String(m?.context_window ?? 128000),
    supports_tools: m?.supports_tools ?? true,
    supports_streaming: m?.supports_streaming ?? true,
    supports_json_schema: m?.supports_json_schema ?? true,
    input_price_per_mtok: trimDecimal(m?.input_price_per_mtok),
    output_price_per_mtok: trimDecimal(m?.output_price_per_mtok),
    default_parameters: m && Object.keys(m.default_parameters).length ? JSON.stringify(m.default_parameters, null, 2) : "{}",
    is_active: m?.is_active ?? true,
  };
}

const FORM_ID = "model-form";

export function ModelDrawer({
  open,
  onOpenChange,
  model,
  providers,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  model: Model | null;
  providers: Provider[];
}) {
  const create = useCreateModel();
  const update = useUpdateModel();
  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title={model ? `Edit ${model.display_name}` : "Add model"}
      description={model ? <span className="font-mono">{model.model_name}</span> : "Register a model offered by one of your providers."}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" form={FORM_ID} variant="primary" loading={create.isPending || update.isPending}>
            {model ? "Save changes" : "Create model"}
          </Button>
        </>
      }
    >
      {open ? (
        <ModelForm key={model?.id ?? "new"} model={model} providers={providers} create={create} update={update} onDone={() => onOpenChange(false)} />
      ) : null}
    </Drawer>
  );
}

function SwitchRow({ id, label, hint, checked, onChange }: { id: string; label: string; hint: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <div>
        <label htmlFor={id} className="text-xs font-medium">
          {label}
        </label>
        <p className="text-xs text-fg-subtle">{hint}</p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onChange} aria-label={label} />
    </div>
  );
}

function ModelForm({
  model,
  providers,
  create,
  update,
  onDone,
}: {
  model: Model | null;
  providers: Provider[];
  create: ReturnType<typeof useCreateModel>;
  update: ReturnType<typeof useUpdateModel>;
  onDone: () => void;
}) {
  const [formError, setFormError] = React.useState<string | null>(null);
  const form = useForm<ModelFormValues>({ resolver: zodResolver(schema), defaultValues: defaults(model, providers) });
  const { register, control, formState } = form;
  const errors = formState.errors;

  async function onSubmit(v: ModelFormValues) {
    setFormError(null);
    const body = {
      display_name: v.display_name.trim(),
      model_name: v.model_name.trim(),
      context_window: Number(v.context_window),
      supports_tools: v.supports_tools,
      supports_streaming: v.supports_streaming,
      supports_json_schema: v.supports_json_schema,
      input_price_per_mtok: v.input_price_per_mtok.trim(),
      output_price_per_mtok: v.output_price_per_mtok.trim(),
      default_parameters: v.default_parameters.trim() ? (JSON.parse(v.default_parameters) as Record<string, unknown>) : {},
      is_active: v.is_active,
    };
    try {
      if (model) {
        await update.mutateAsync({ id: model.id, body });
        toast.success(`Saved ${body.display_name}`);
      } else {
        await create.mutateAsync({ ...body, provider_id: v.provider_id });
        toast.success(`Added ${body.display_name}`);
      }
      onDone();
    } catch (err) {
      setFormError(applyServerErrors(err, form.setError, FIELDS));
    }
  }

  return (
    <form id={FORM_ID} onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
      <Field label="Provider" htmlFor="m-provider" required error={errors.provider_id?.message} hint={model ? "A model cannot move between providers." : undefined}>
        <Controller
          control={control}
          name="provider_id"
          render={({ field }) => (
            <Select
              id="m-provider"
              value={field.value || undefined}
              onValueChange={field.onChange}
              disabled={!!model}
              placeholder="Choose a provider"
              aria-invalid={!!errors.provider_id}
              options={providers.map((p) => ({ value: p.id, label: p.name, description: providerTypeLabel(p.provider_type) }))}
            />
          )}
        />
      </Field>

      <FieldRow>
        <Field label="Display name" htmlFor="m-display" required error={errors.display_name?.message}>
          <Input id="m-display" autoFocus placeholder="GPT-5 mini" aria-invalid={!!errors.display_name} {...register("display_name")} />
        </Field>
        <Field label="Model name" htmlFor="m-name" required error={errors.model_name?.message} hint="Exactly as the provider's API expects it.">
          <Input id="m-name" className="font-mono text-xs" spellCheck={false} placeholder="gpt-5-mini" aria-invalid={!!errors.model_name} {...register("model_name")} />
        </Field>
      </FieldRow>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Field label="Context window" htmlFor="m-ctx" error={errors.context_window?.message} hint="Tokens">
          <Input id="m-ctx" inputMode="numeric" className="tabular" aria-invalid={!!errors.context_window} {...register("context_window")} />
        </Field>
        <Field label="Input price" htmlFor="m-in" error={errors.input_price_per_mtok?.message} hint="USD per million tokens">
          <Input id="m-in" inputMode="decimal" className="tabular" aria-invalid={!!errors.input_price_per_mtok} {...register("input_price_per_mtok")} />
        </Field>
        <Field label="Output price" htmlFor="m-out" error={errors.output_price_per_mtok?.message} hint="USD per million tokens">
          <Input id="m-out" inputMode="decimal" className="tabular" aria-invalid={!!errors.output_price_per_mtok} {...register("output_price_per_mtok")} />
        </Field>
      </div>

      <div className="flex flex-col divide-y divide-border border-y border-border">
        <Controller
          control={control}
          name="supports_tools"
          render={({ field }) => (
            <SwitchRow id="m-tools" label="Supports tool calls" hint="Agent nodes only offer MCP tools to models that support them." checked={field.value} onChange={field.onChange} />
          )}
        />
        <Controller
          control={control}
          name="supports_json_schema"
          render={({ field }) => (
            <SwitchRow id="m-json" label="Supports JSON schema output" hint="Structured output is enforced by the provider instead of by parsing." checked={field.value} onChange={field.onChange} />
          )}
        />
        <Controller
          control={control}
          name="supports_streaming"
          render={({ field }) => <SwitchRow id="m-stream" label="Supports streaming" hint="Tokens are streamed to the execution view as they arrive." checked={field.value} onChange={field.onChange} />}
        />
        <Controller
          control={control}
          name="is_active"
          render={({ field }) => <SwitchRow id="m-active" label="Active" hint="Inactive models cannot be selected in pipelines." checked={field.value} onChange={field.onChange} />}
        />
      </div>

      <Field label="Default parameters" error={errors.default_parameters?.message} hint="JSON object merged under each node's own parameters, for example max_tokens or temperature.">
        <Controller
          control={control}
          name="default_parameters"
          render={({ field }) => (
            <CodeEditor
              value={field.value}
              onChange={field.onChange}
              language="json"
              minHeight="140px"
              maxHeight="320px"
              ariaLabel="Default parameters (JSON)"
              invalid={!!errors.default_parameters}
            />
          )}
        />
      </Field>

      {formError ? (
        <p role="alert" className="rounded-md bg-danger-bg px-3 py-2 text-sm text-danger">
          {formError}
        </p>
      ) : null}
    </form>
  );
}
