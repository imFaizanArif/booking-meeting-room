"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import * as React from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { CodeEditor } from "@/components/ui/code-editor";
import { Field, FieldRow } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Drawer } from "@/components/ui/overlay";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/toggles";
import { applyServerErrors, FormError } from "@/components/ui-extra/form-error";
import { SegmentedControl } from "@/components/ui-extra/segmented";
import { ApiError, type Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { describeCron, describeInterval } from "./describe";
import { useSaveSchedule } from "./mutations";
import { usePipelineOptions } from "./queries";
import { TimezoneField } from "./timezone-field";

type ScheduleOut = Schemas["ScheduleOut"];

const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;

export const scheduleFormSchema = z
  .object({
    pipeline_id: z.string().min(1, "Choose a pipeline"),
    name: z.string().trim().min(1, "Give the schedule a name").max(200, "200 characters at most"),
    kind: z.enum(["interval", "daily", "cron"]),
    interval_minutes: z.string(),
    daily_time: z.string(),
    cron: z.string(),
    timezone: z.string().trim().min(1, "Choose a timezone"),
    input: z.string(),
    overlap_policy: z.enum(["skip", "queue"]),
    is_active: z.boolean(),
  })
  .superRefine((v, ctx) => {
    if (v.kind === "interval") {
      const n = Number(v.interval_minutes);
      if (!/^\d+$/.test(v.interval_minutes.trim()) || n < 1) ctx.addIssue({ code: "custom", path: ["interval_minutes"], message: "Whole minutes, at least 1" });
    }
    if (v.kind === "daily" && !TIME_RE.test(v.daily_time.trim())) {
      ctx.addIssue({ code: "custom", path: ["daily_time"], message: "Use 24h HH:MM, for example 09:00" });
    }
    if (v.kind === "cron" && v.cron.trim().split(/\s+/).length !== 5) {
      ctx.addIssue({ code: "custom", path: ["cron"], message: "Five fields: minute hour day month weekday" });
    }
    try {
      const parsed: unknown = JSON.parse(v.input || "{}");
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        ctx.addIssue({ code: "custom", path: ["input"], message: "Input must be a JSON object" });
      }
    } catch {
      ctx.addIssue({ code: "custom", path: ["input"], message: "Not valid JSON" });
    }
  });

export type ScheduleFormValues = z.infer<typeof scheduleFormSchema>;

const FIELDS = ["pipeline_id", "name", "kind", "interval_minutes", "daily_time", "cron", "timezone", "input", "overlap_policy", "is_active"] as const;

function defaults(schedule: ScheduleOut | null): ScheduleFormValues {
  if (!schedule) {
    let tz = "UTC";
    try {
      tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    } catch {
      /* keep UTC */
    }
    return {
      pipeline_id: "",
      name: "",
      kind: "daily",
      interval_minutes: "60",
      daily_time: "09:00",
      cron: "0 9 * * 1-5",
      timezone: tz,
      input: "{}",
      overlap_policy: "skip",
      is_active: true,
    };
  }
  return {
    pipeline_id: schedule.pipeline_id,
    name: schedule.name,
    kind: schedule.kind,
    interval_minutes: schedule.interval_seconds ? String(Math.max(1, Math.round(schedule.interval_seconds / 60))) : "60",
    daily_time: schedule.daily_time ?? "09:00",
    cron: schedule.cron ?? "0 9 * * 1-5",
    timezone: schedule.timezone,
    input: JSON.stringify(schedule.input ?? {}, null, 2),
    overlap_policy: schedule.overlap_policy,
    is_active: schedule.is_active,
  };
}

export function toBody(v: ScheduleFormValues): Schemas["ScheduleIn"] {
  return {
    pipeline_id: v.pipeline_id,
    name: v.name.trim(),
    kind: v.kind,
    interval_seconds: v.kind === "interval" ? Number(v.interval_minutes) * 60 : null,
    daily_time: v.kind === "daily" ? v.daily_time.trim() : null,
    cron: v.kind === "cron" ? v.cron.trim().replace(/\s+/g, " ") : null,
    timezone: v.timezone.trim(),
    input: JSON.parse(v.input || "{}") as Record<string, unknown>,
    overlap_policy: v.overlap_policy,
    is_active: v.is_active,
  };
}

const OVERLAP = [
  { value: "skip" as const, label: "Skip", description: "If the previous run is still going, drop this fire." },
  { value: "queue" as const, label: "Queue", description: "Start this run anyway; runs may overlap." },
];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  schedule: ScheduleOut | null;
}

export function ScheduleDrawer({ open, onOpenChange, schedule }: Props) {
  // Owned here so the footer (outside the <form>) can show the pending state.
  const save = useSaveSchedule();
  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title={schedule ? "Edit schedule" : "New schedule"}
      description={schedule ? schedule.name : "Run a pipeline on an interval, at a time of day, or on a cron expression."}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" form="schedule-form" variant="primary" loading={save.isPending}>
            {schedule ? "Save schedule" : "Create schedule"}
          </Button>
        </>
      }
    >
      {open ? <ScheduleForm key={schedule?.id ?? "new"} schedule={schedule} save={save} onDone={() => onOpenChange(false)} /> : null}
    </Drawer>
  );
}

function ScheduleForm({ schedule, save, onDone }: { schedule: ScheduleOut | null; save: ReturnType<typeof useSaveSchedule>; onDone: () => void }) {
  const pipelines = usePipelineOptions();
  const [submitError, setSubmitError] = React.useState<unknown>(null);
  const form = useForm<ScheduleFormValues>({ resolver: zodResolver(scheduleFormSchema), defaultValues: defaults(schedule) });
  const { register, control, watch, formState, handleSubmit, setError } = form;
  const errors = formState.errors;
  const kind = watch("kind");
  const cron = watch("cron");
  const minutes = watch("interval_minutes");

  const pipelineOptions = (pipelines.data ?? [])
    .filter((p) => !p.is_archived || p.id === schedule?.pipeline_id)
    .map((p) => ({ value: p.id, label: p.name, description: p.latest_version_number ? `v${p.latest_version_number} · ${p.node_count} nodes` : "No published version" }));

  async function onSubmit(values: ScheduleFormValues) {
    setSubmitError(null);
    try {
      await save.mutateAsync({ id: schedule?.id, body: toBody(values) });
      onDone();
    } catch (err) {
      const leftover = applyServerErrors(err, setError, FIELDS, { interval_seconds: "interval_minutes" });
      const placedAll = err instanceof ApiError && err.fields.length > 0 && leftover.length === 0;
      setSubmitError(placedAll ? null : err);
    }
  }

  const cronText = kind === "cron" ? describeCron(cron) : null;
  const intervalText = kind === "interval" && /^\d+$/.test(minutes) && Number(minutes) > 0 ? describeInterval(Number(minutes) * 60) : null;

  return (
    <form id="schedule-form" onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <Field label="Pipeline" htmlFor="s-pipeline" required error={errors.pipeline_id?.message} hint={pipelines.isError ? "Could not load pipelines." : undefined}>
          <Controller
            control={control}
            name="pipeline_id"
            render={({ field }) => (
              <Select
                id="s-pipeline"
                value={field.value || undefined}
                onValueChange={field.onChange}
                options={pipelineOptions}
                placeholder={pipelines.isPending ? "Loading pipelines…" : pipelineOptions.length ? "Choose a pipeline" : "No pipelines yet"}
                disabled={pipelines.isPending}
                aria-invalid={!!errors.pipeline_id}
              />
            )}
          />
        </Field>

        <Field label="Name" htmlFor="s-name" required error={errors.name?.message}>
          <Input id="s-name" autoComplete="off" placeholder="Weekday mornings" aria-invalid={!!errors.name} {...register("name")} />
        </Field>

        <div className="flex flex-col gap-2">
          <span id="s-kind-label" className="text-xs font-medium">
            Runs
          </span>
          <Controller
            control={control}
            name="kind"
            render={({ field }) => (
              <SegmentedControl
                aria-labelledby="s-kind-label"
                value={field.value}
                onValueChange={field.onChange}
                className="self-start"
                options={[
                  { value: "interval", label: "Interval" },
                  { value: "daily", label: "Daily" },
                  { value: "cron", label: "Cron" },
                ]}
              />
            )}
          />
        </div>

        {kind === "interval" ? (
          <Field label="Every" htmlFor="s-interval" required error={errors.interval_minutes?.message} hint={intervalText ?? "Minutes between runs. Minimum 1."}>
            <div className="flex items-center gap-2">
              <Input id="s-interval" type="number" inputMode="numeric" min={1} step={1} className="w-32 tabular" aria-invalid={!!errors.interval_minutes} {...register("interval_minutes")} />
              <span className="text-sm text-fg-muted">minutes</span>
            </div>
          </Field>
        ) : null}

        {kind === "daily" ? (
          <Field label="At" htmlFor="s-daily" required error={errors.daily_time?.message} hint="24-hour time in the schedule's timezone.">
            <Input id="s-daily" placeholder="09:00" className="w-32 font-mono tabular" autoComplete="off" aria-invalid={!!errors.daily_time} {...register("daily_time")} />
          </Field>
        ) : null}

        {kind === "cron" ? (
          <Field
            label="Cron expression"
            htmlFor="s-cron"
            required
            error={errors.cron?.message}
            hint={
              <>
                <span className="font-mono">minute hour day month weekday</span>, e.g. <span className="font-mono">45 8 * * 1-5</span>.{" "}
                {cronText ? <span className="text-fg-muted">Reads as: {cronText}.</span> : null}
              </>
            }
          >
            <Input id="s-cron" className="font-mono" autoComplete="off" spellCheck={false} placeholder="0 9 * * 1-5" aria-invalid={!!errors.cron} {...register("cron")} />
          </Field>
        ) : null}

        <Field
          label="Timezone"
          htmlFor="s-tz"
          required
          error={errors.timezone?.message}
          hint={kind === "interval" ? "Intervals are not affected by the timezone; it is kept for reference." : "Daily and cron times are evaluated in this zone, including daylight saving."}
        >
          <Controller
            control={control}
            name="timezone"
            render={({ field }) => <TimezoneField id="s-tz" value={field.value} onChange={field.onChange} invalid={!!errors.timezone} />}
          />
        </Field>

        <Field label="Input" htmlFor="s-input" error={errors.input?.message} hint="JSON object passed to the pipeline as its input on every run.">
          <Controller
            control={control}
            name="input"
            render={({ field }) => (
              <CodeEditor ariaLabel="Schedule input JSON" language="json" value={field.value} onChange={field.onChange} minHeight="96px" maxHeight="280px" invalid={!!errors.input} />
            )}
          />
        </Field>

        <fieldset className="flex flex-col gap-1.5">
          <legend className="mb-1 text-xs font-medium">When a run is still in progress</legend>
          <Controller
            control={control}
            name="overlap_policy"
            render={({ field }) => (
              <div role="radiogroup" aria-label="Overlap policy" className="flex flex-col gap-1.5">
                {OVERLAP.map((o) => (
                  <label
                    key={o.value}
                    className={cn(
                      "flex cursor-pointer items-start gap-2.5 rounded-md border px-3 py-2",
                      field.value === o.value ? "border-fg-subtle bg-subtle" : "border-border hover:bg-subtle",
                    )}
                  >
                    <input
                      type="radio"
                      name="overlap_policy"
                      value={o.value}
                      checked={field.value === o.value}
                      onChange={() => field.onChange(o.value)}
                      className="mt-1 accent-[var(--ink)]"
                    />
                    <span>
                      <span className="block text-sm font-medium">{o.label}</span>
                      <span className="block text-xs text-fg-muted">{o.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            )}
          />
        </fieldset>

        <div className="flex items-start justify-between gap-4 border-t border-border pt-4">
          <div>
            <label htmlFor="s-active" className="text-xs font-medium">
              Active
            </label>
            <p className="text-xs text-fg-subtle">Paused schedules keep their settings but never fire.</p>
          </div>
          <Controller control={control} name="is_active" render={({ field }) => <Switch id="s-active" checked={field.value} onCheckedChange={field.onChange} />} />
        </div>

        <FormError error={submitError} />
    </form>
  );
}
