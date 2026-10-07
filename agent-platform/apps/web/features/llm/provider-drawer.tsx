"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import * as React from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field, FieldRow } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Drawer } from "@/components/ui/overlay";
import { Select } from "@/components/ui/select";
import { Checkbox, Switch } from "@/components/ui/toggles";
import { applyServerErrors } from "@/components/ui-extra/form-errors";
import { SecretState } from "@/components/ui-extra/secret-state";

import { useCreateProvider, useUpdateProvider } from "./mutations";
import { KEYLESS, PROVIDER_TYPES, type Provider, type ProviderType } from "./queries";

const optionalInt = (min: number, max: number) =>
  z
    .string()
    .trim()
    .refine((v) => v === "" || (/^\d+$/.test(v) && Number(v) >= min && Number(v) <= max), `Enter a whole number from ${min} to ${max.toLocaleString("en")}`);

const baseSchema = z.object({
  name: z.string().trim().min(1, "Enter a name").max(200, "Keep the name under 200 characters"),
  provider_type: z.enum(["openai", "anthropic", "gemini", "ollama", "fake"]),
  base_url: z
    .string()
    .trim()
    .max(500)
    .refine((v) => v === "" || /^https?:\/\/\S+$/.test(v), "Enter a full URL starting with http:// or https://"),
  api_key: z.string(),
  clear_api_key: z.boolean(),
  is_active: z.boolean(),
  requests_per_minute: optionalInt(1, 100_000),
  max_concurrency: optionalInt(1, 1000),
});
export type ProviderFormValues = z.infer<typeof baseSchema>;

const FIELDS = ["name", "provider_type", "base_url", "api_key", "is_active", "requests_per_minute", "max_concurrency"] as const;

function defaults(p: Provider | null): ProviderFormValues {
  return {
    name: p?.name ?? "",
    provider_type: p?.provider_type ?? "openai",
    base_url: p?.base_url ?? "",
    api_key: "",
    clear_api_key: false,
    is_active: p?.is_active ?? false,
    requests_per_minute: p?.requests_per_minute != null ? String(p.requests_per_minute) : "",
    max_concurrency: p?.max_concurrency != null ? String(p.max_concurrency) : "",
  };
}

const toInt = (v: string) => (v.trim() === "" ? null : Number(v));

const FORM_ID = "provider-form";

export function ProviderDrawer({ open, onOpenChange, provider }: { open: boolean; onOpenChange: (open: boolean) => void; provider: Provider | null }) {
  const create = useCreateProvider();
  const update = useUpdateProvider();
  const pending = create.isPending || update.isPending;
  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title={provider ? `Edit ${provider.name}` : "Add provider"}
      description={provider ? "Changes apply to new LLM calls immediately." : "Connect an LLM API. Keys are stored encrypted and never shown again."}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" form={FORM_ID} variant="primary" loading={pending}>
            {provider ? "Save changes" : "Create provider"}
          </Button>
        </>
      }
    >
      {open ? <ProviderForm key={provider?.id ?? "new"} provider={provider} create={create} update={update} onDone={() => onOpenChange(false)} /> : null}
    </Drawer>
  );
}

function ProviderForm({
  provider,
  create,
  update,
  onDone,
}: {
  provider: Provider | null;
  create: ReturnType<typeof useCreateProvider>;
  update: ReturnType<typeof useUpdateProvider>;
  onDone: () => void;
}) {
  const [formError, setFormError] = React.useState<string | null>(null);
  const keySet = !!provider?.api_key.is_set;

  const schema = React.useMemo(
    () =>
      baseSchema.superRefine((v, ctx) => {
        const willHaveKey = v.api_key.trim() !== "" || (keySet && !v.clear_api_key);
        if (v.is_active && !KEYLESS.has(v.provider_type) && !willHaveKey) {
          ctx.addIssue({ code: "custom", path: ["api_key"], message: "Add an API key before activating this provider" });
        }
      }),
    [keySet],
  );

  const form = useForm<ProviderFormValues>({ resolver: zodResolver(schema), defaultValues: defaults(provider) });
  const { register, control, watch, formState } = form;
  const errors = formState.errors;
  const type = watch("provider_type");
  const clearKey = watch("clear_api_key");
  const keyless = KEYLESS.has(type);

  async function onSubmit(v: ProviderFormValues) {
    setFormError(null);
    const common = {
      name: v.name.trim(),
      base_url: v.base_url.trim() || null,
      is_active: v.is_active,
      requests_per_minute: toInt(v.requests_per_minute),
      max_concurrency: toInt(v.max_concurrency),
    };
    const apiKey = v.api_key.trim();
    try {
      if (provider) {
        await update.mutateAsync({
          id: provider.id,
          body: { ...common, clear_api_key: v.clear_api_key && !apiKey, ...(apiKey ? { api_key: apiKey } : {}) },
        });
        toast.success(`Saved ${common.name}`);
      } else {
        await create.mutateAsync({ ...common, provider_type: v.provider_type, clear_api_key: false, ...(apiKey ? { api_key: apiKey } : {}) });
        toast.success(`Added ${common.name}`);
      }
      onDone();
    } catch (err) {
      setFormError(applyServerErrors(err, form.setError, FIELDS));
    }
  }

  return (
    <form id={FORM_ID} onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
      <FieldRow>
        <Field label="Name" htmlFor="p-name" required error={errors.name?.message}>
          <Input id="p-name" autoFocus aria-invalid={!!errors.name} {...register("name")} />
        </Field>
        <Field label="Type" htmlFor="p-type" hint={provider ? "The type cannot change after creation." : undefined}>
          <Controller
            control={control}
            name="provider_type"
            render={({ field }) => (
              <Select
                id="p-type"
                value={field.value}
                onValueChange={(v) => field.onChange(v as ProviderType)}
                disabled={!!provider}
                options={PROVIDER_TYPES.map((t) => ({ value: t.value, label: t.label, description: t.description }))}
              />
            )}
          />
        </Field>
      </FieldRow>

      <Field
        label="Base URL"
        htmlFor="p-base-url"
        error={errors.base_url?.message}
        hint={type === "ollama" ? "Usually http://localhost:11434" : "Leave empty to use the provider's default endpoint."}
      >
        <Input id="p-base-url" className="font-mono text-xs" placeholder="https://" aria-invalid={!!errors.base_url} {...register("base_url")} />
      </Field>

      <div className="flex flex-col gap-2 rounded-md border border-border p-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs font-medium">API key</span>
          {provider ? <SecretState state={provider.api_key} setLabel="Key set" unsetLabel="No key stored" /> : null}
        </div>
        <Field
          label={keySet ? "Replace key" : "Key"}
          htmlFor="p-api-key"
          error={errors.api_key?.message}
          hint={
            keyless
              ? "Optional for this provider type."
              : keySet
                ? "Leave empty to keep the stored key. The value is write-only."
                : "Write-only. It is encrypted at rest and never returned by the API."
          }
        >
          <Input
            id="p-api-key"
            type="password"
            autoComplete="new-password"
            spellCheck={false}
            className="font-mono text-xs"
            placeholder={keySet ? "Paste a new key to replace it" : "sk-…"}
            disabled={clearKey}
            aria-invalid={!!errors.api_key}
            {...register("api_key")}
          />
        </Field>
        {keySet ? (
          <Controller
            control={control}
            name="clear_api_key"
            render={({ field }) => (
              <label className="flex items-center gap-2 text-xs text-fg-muted">
                <Checkbox checked={field.value} onCheckedChange={(c) => field.onChange(c === true)} aria-label="Remove the stored key" />
                Remove the stored key
              </label>
            )}
          />
        ) : null}
      </div>

      <FieldRow>
        <Field label="Requests per minute" htmlFor="p-rpm" error={errors.requests_per_minute?.message} hint="Empty means no limit.">
          <Input id="p-rpm" inputMode="numeric" className="tabular" aria-invalid={!!errors.requests_per_minute} {...register("requests_per_minute")} />
        </Field>
        <Field label="Max concurrent calls" htmlFor="p-conc" error={errors.max_concurrency?.message} hint="Empty means no limit.">
          <Input id="p-conc" inputMode="numeric" className="tabular" aria-invalid={!!errors.max_concurrency} {...register("max_concurrency")} />
        </Field>
      </FieldRow>

      <Controller
        control={control}
        name="is_active"
        render={({ field }) => (
          <div className="flex items-start justify-between gap-4 border-t border-border pt-4">
            <div>
              <label htmlFor="p-active" className="text-xs font-medium">
                Active
              </label>
              <p className="text-xs text-fg-subtle">Inactive providers and their models cannot be used by pipelines.</p>
            </div>
            <Switch id="p-active" checked={field.value} onCheckedChange={field.onChange} aria-label="Provider active" />
          </div>
        )}
      />

      {formError ? (
        <p role="alert" className="rounded-md bg-danger-bg px-3 py-2 text-sm text-danger">
          {formError}
        </p>
      ) : null}
    </form>
  );
}
