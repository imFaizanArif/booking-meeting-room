"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { TerminalSquare } from "lucide-react";
import * as React from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field, FieldRow } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Drawer, Modal } from "@/components/ui/overlay";
import { Select } from "@/components/ui/select";
import { StatusIndicator } from "@/components/ui/status";
import { Switch } from "@/components/ui/toggles";
import { applyServerErrors } from "@/components/ui-extra/form-errors";
import { Gate } from "@/components/ui-extra/gate";
import type { Schemas } from "@/lib/api/client";
import { dateTime, relativeTime } from "@/lib/format";

import { useCreateServer, useUpdateServer } from "./mutations";
import { commandLine, TRANSPORTS, type Server, type Transport } from "./queries";
import { rowsFromState, rowsToPayload, SecretMapEditor, validateRows, type SecretRow } from "./secret-map-editor";

const decimalIn = (min: number, max: number, label: string) =>
  z
    .string()
    .trim()
    .refine((v) => /^\d+(\.\d+)?$/.test(v) && Number(v) >= min && Number(v) <= max, `${label} must be between ${min} and ${max} seconds`);

const schema = z
  .object({
    name: z.string().trim().min(1, "Enter a name").max(200),
    slug: z
      .string()
      .trim()
      .refine((v) => v === "" || /^[a-z][a-z0-9_]{1,40}$/.test(v), "2–41 characters: lowercase letters, digits and _, starting with a letter"),
    description: z.string(),
    transport: z.enum(["stdio", "streamable_http", "sse_legacy"]),
    command: z.string(),
    args: z.string(),
    cwd: z.string(),
    url: z.string(),
    env: z.array(z.custom<SecretRow>()),
    headers: z.array(z.custom<SecretRow>()),
    isolation: z.enum(["shared", "per_execution"]),
    is_active: z.boolean(),
    connect_timeout_s: decimalIn(1, 300, "Connect timeout"),
    call_timeout_s: decimalIn(1, 3600, "Call timeout"),
    requests_per_minute: z
      .string()
      .trim()
      .refine((v) => v === "" || (/^\d+$/.test(v) && Number(v) >= 1), "Enter a whole number of at least 1, or leave empty"),
  })
  .superRefine((v, ctx) => {
    if (v.transport === "stdio") {
      if (!v.command.trim()) ctx.addIssue({ code: "custom", path: ["command"], message: "Enter the executable to run" });
    } else {
      const url = v.url.trim();
      if (!url) ctx.addIssue({ code: "custom", path: ["url"], message: "Enter the server URL" });
      else if (!/^https?:\/\/\S+$/.test(url)) ctx.addIssue({ code: "custom", path: ["url"], message: "Enter a full URL starting with http:// or https://" });
    }
    if (validateRows(v.transport === "stdio" ? v.env : [], "env")) ctx.addIssue({ code: "custom", path: ["env"], message: "Fix the highlighted variables" });
    if (validateRows(v.transport === "stdio" ? [] : v.headers, "headers")) ctx.addIssue({ code: "custom", path: ["headers"], message: "Fix the highlighted headers" });
  });
export type ServerFormValues = z.infer<typeof schema>;

const FIELDS = ["name", "slug", "description", "transport", "command", "args", "cwd", "url", "is_active", "connect_timeout_s", "call_timeout_s", "requests_per_minute"] as const;

function defaults(s: Server | null): ServerFormValues {
  return {
    name: s?.name ?? "",
    slug: s?.slug ?? "",
    description: s?.description ?? "",
    transport: s?.transport ?? "streamable_http",
    command: s?.command ?? "",
    args: (s?.args ?? []).join("\n"),
    cwd: s?.cwd ?? "",
    url: s?.url ?? "",
    env: rowsFromState(s?.env),
    headers: rowsFromState(s?.headers),
    isolation: s?.isolation ?? "shared",
    is_active: s?.is_active ?? false,
    connect_timeout_s: String(s?.connect_timeout_s ?? 20),
    call_timeout_s: String(s?.call_timeout_s ?? 60),
    requests_per_minute: s?.requests_per_minute != null ? String(s.requests_per_minute) : "",
  };
}

/** One argument per line. Lines are kept verbatim (spaces included); blank lines are dropped. */
export function parseArgs(text: string): string[] {
  return text
    .split("\n")
    .map((l) => l.replace(/\r$/, ""))
    .filter((l) => l.trim() !== "");
}

export function toBody(v: ServerFormValues, confirm: boolean): Schemas["MCPServerIn"] {
  const stdio = v.transport === "stdio";
  const env = stdio ? rowsToPayload(v.env) : { values: {}, keep: [] };
  const headers = stdio ? { values: {}, keep: [] } : rowsToPayload(v.headers);
  return {
    name: v.name.trim(),
    slug: v.slug.trim() || null,
    description: v.description.trim() || null,
    transport: v.transport,
    command: stdio ? v.command.trim() : null,
    args: stdio ? parseArgs(v.args) : [],
    cwd: stdio ? v.cwd.trim() || null : null,
    url: stdio ? null : v.url.trim(),
    env: env.values,
    env_keep: env.keep,
    headers: headers.values,
    headers_keep: headers.keep,
    isolation: v.isolation,
    is_active: v.is_active,
    connect_timeout_s: Number(v.connect_timeout_s),
    call_timeout_s: Number(v.call_timeout_s),
    requests_per_minute: v.requests_per_minute.trim() ? Number(v.requests_per_minute) : null,
    confirm_command: stdio && confirm,
  };
}

const FORM_ID = "mcp-server-form";
const STDIO_OWNER_ONLY = "Only workspace owners can configure stdio servers, because they run commands on the worker host.";

export function ServerDrawer({
  open,
  onOpenChange,
  server,
  role,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  server: Server | null;
  role: string | undefined;
}) {
  const create = useCreateServer();
  const update = useUpdateServer();
  const [transport, setTransport] = React.useState<Transport>(server?.transport ?? "streamable_http");
  const isOwner = role === "owner";
  const canEdit = role === "owner" || role === "operator";
  const needsOwner = transport === "stdio" || server?.transport === "stdio";
  const allowed = canEdit && (!needsOwner || isOwner);

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title={server ? `Edit ${server.name}` : "Add MCP server"}
      description={
        server ? (
          <span className="font-mono">{server.slug}</span>
        ) : (
          "Connect a Model Context Protocol server. Its tools start disabled until you enable them."
        )
      }
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Gate allowed={allowed} reason={canEdit ? STDIO_OWNER_ONLY : "Viewers cannot change MCP servers."}>
            <Button type="submit" form={FORM_ID} variant="primary" loading={create.isPending || update.isPending}>
              {server ? "Save changes" : "Create server"}
            </Button>
          </Gate>
        </>
      }
    >
      {open ? (
        <ServerForm
          key={server?.id ?? "new"}
          server={server}
          create={create}
          update={update}
          onTransportChange={setTransport}
          onDone={() => onOpenChange(false)}
        />
      ) : null}
    </Drawer>
  );
}

function SubHeading({ children }: { children: React.ReactNode }) {
  return <h3 className="border-b border-border pb-1.5 text-xs font-semibold text-fg-muted">{children}</h3>;
}

function ServerForm({
  server,
  create,
  update,
  onTransportChange,
  onDone,
}: {
  server: Server | null;
  create: ReturnType<typeof useCreateServer>;
  update: ReturnType<typeof useUpdateServer>;
  onTransportChange: (t: Transport) => void;
  onDone: () => void;
}) {
  const [formError, setFormError] = React.useState<string | null>(null);
  const [confirming, setConfirming] = React.useState<ServerFormValues | null>(null);
  const form = useForm<ServerFormValues>({ resolver: zodResolver(schema), defaultValues: defaults(server) });
  const { register, control, formState, setValue } = form;
  const errors = formState.errors;
  const [transport, envRows, headerRows, command, args] = useWatch({ control, name: ["transport", "env", "headers", "command", "args"] });
  const stdio = transport === "stdio";
  const showRowErrors = formState.submitCount > 0;

  React.useEffect(() => onTransportChange(transport), [transport, onTransportChange]);

  async function save(v: ServerFormValues, confirm: boolean) {
    setFormError(null);
    const body = toBody(v, confirm);
    try {
      if (server) await update.mutateAsync({ id: server.id, body });
      else await create.mutateAsync(body);
      toast.success(server ? `Saved ${body.name}` : `Added ${body.name}`);
      setConfirming(null);
      onDone();
    } catch (err) {
      setConfirming(null);
      setFormError(applyServerErrors(err, form.setError, FIELDS));
    }
  }

  function onSubmit(v: ServerFormValues) {
    // Activating a stdio server runs a command on the worker host: show it verbatim first.
    if (v.transport === "stdio" && v.is_active) setConfirming(v);
    else void save(v, false);
  }

  return (
    <>
      <form id={FORM_ID} onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-5" noValidate>
        {server ? (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-border bg-subtle px-3 py-2 text-xs">
            <StatusIndicator kind="server" value={server.status} />
            <span className="text-fg-muted">Last connected {relativeTime(server.last_connected_at)}</span>
            {server.status_message ? <span className="w-full text-fg-muted">{server.status_message}</span> : null}
          </div>
        ) : null}

        <div className="flex flex-col gap-3">
          <FieldRow>
            <Field label="Name" htmlFor="s-name" required error={errors.name?.message}>
              <Input id="s-name" autoFocus aria-invalid={!!errors.name} {...register("name")} />
            </Field>
            <Field
              label="Slug"
              htmlFor="s-slug"
              error={errors.slug?.message}
              hint={server ? "Prefixes tool names. Changing it renames every tool." : "Prefixes tool names. Generated from the name if empty."}
            >
              <Input id="s-slug" className="font-mono text-xs" spellCheck={false} placeholder="github" aria-invalid={!!errors.slug} {...register("slug")} />
            </Field>
          </FieldRow>
          <Field label="Description" htmlFor="s-desc" error={errors.description?.message}>
            <Input id="s-desc" placeholder="What this server gives agents access to" {...register("description")} />
          </Field>
        </div>

        <div className="flex flex-col gap-3">
          <SubHeading>Connection</SubHeading>
          <Field label="Transport" htmlFor="s-transport">
            <Controller
              control={control}
              name="transport"
              render={({ field }) => (
                <Select
                  id="s-transport"
                  value={field.value}
                  onValueChange={(t) => field.onChange(t as Transport)}
                  options={TRANSPORTS.map((t) => ({ value: t.value, label: t.label, description: t.description }))}
                />
              )}
            />
          </Field>

          {stdio ? (
            <>
              <Field label="Command" htmlFor="s-command" required error={errors.command?.message} hint="Absolute path to the executable. No shell is involved.">
                <Input id="s-command" className="font-mono text-xs" spellCheck={false} placeholder="/usr/bin/npx" aria-invalid={!!errors.command} {...register("command")} />
              </Field>
              <Field label="Arguments" htmlFor="s-args" error={errors.args?.message} hint="One argument per line, passed exactly as written.">
                <Textarea id="s-args" rows={4} className="font-mono text-xs" spellCheck={false} placeholder={"-y\n@modelcontextprotocol/server-filesystem\n/srv/data"} {...register("args")} />
              </Field>
              <Field label="Working directory" htmlFor="s-cwd" error={errors.cwd?.message} hint="Optional. Defaults to the worker's working directory.">
                <Input id="s-cwd" className="font-mono text-xs" spellCheck={false} {...register("cwd")} />
              </Field>
              {command.trim() ? (
                <div className="flex flex-col gap-1">
                  <span className="text-xs font-medium">Command line</span>
                  <pre className="scrollbar-thin overflow-x-auto whitespace-pre-wrap break-all rounded-md border border-border bg-subtle px-3 py-2 font-mono text-xs">
                    {commandLine(command.trim(), parseArgs(args))}
                  </pre>
                </div>
              ) : null}
            </>
          ) : (
            <Field label="URL" htmlFor="s-url" required error={errors.url?.message} hint={transport === "sse_legacy" ? "The SSE endpoint, usually ending in /sse." : "The MCP endpoint, usually ending in /mcp."}>
              <Input id="s-url" className="font-mono text-xs" spellCheck={false} placeholder="https://mcp.example.com/mcp" aria-invalid={!!errors.url} {...register("url")} />
            </Field>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <SubHeading>{stdio ? "Environment variables" : "Headers"}</SubHeading>
          <p className="text-xs text-fg-subtle">
            {stdio
              ? "Only these variables are passed to the process. Values are write-only and stored encrypted."
              : "Sent with every request, for example Authorization. Values are write-only and stored encrypted."}
          </p>
          <Controller
            control={control}
            name={stdio ? "env" : "headers"}
            render={({ field }) => (
              <SecretMapEditor
                kind={stdio ? "env" : "headers"}
                idPrefix={stdio ? "env" : "hdr"}
                rows={field.value}
                onChange={(rows) => setValue(stdio ? "env" : "headers", rows, { shouldValidate: showRowErrors, shouldDirty: true })}
                errors={showRowErrors ? validateRows(stdio ? envRows : headerRows, stdio ? "env" : "headers") : null}
              />
            )}
          />
        </div>

        <div className="flex flex-col gap-3">
          <SubHeading>Runtime</SubHeading>
          <Field label="Isolation" htmlFor="s-iso" hint="Per execution starts a separate connection for every run, so no state is shared between runs.">
            <Controller
              control={control}
              name="isolation"
              render={({ field }) => (
                <Select
                  id="s-iso"
                  value={field.value}
                  onValueChange={field.onChange}
                  options={[
                    { value: "shared", label: "Shared connection" },
                    { value: "per_execution", label: "One connection per execution" },
                  ]}
                />
              )}
            />
          </Field>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Field label="Connect timeout" htmlFor="s-ct" error={errors.connect_timeout_s?.message} hint="Seconds">
              <Input id="s-ct" inputMode="decimal" className="tabular" aria-invalid={!!errors.connect_timeout_s} {...register("connect_timeout_s")} />
            </Field>
            <Field label="Call timeout" htmlFor="s-callt" error={errors.call_timeout_s?.message} hint="Seconds per tool call">
              <Input id="s-callt" inputMode="decimal" className="tabular" aria-invalid={!!errors.call_timeout_s} {...register("call_timeout_s")} />
            </Field>
            <Field label="Requests per minute" htmlFor="s-rpm" error={errors.requests_per_minute?.message} hint="Empty means no limit">
              <Input id="s-rpm" inputMode="numeric" className="tabular" aria-invalid={!!errors.requests_per_minute} {...register("requests_per_minute")} />
            </Field>
          </div>
          <Controller
            control={control}
            name="is_active"
            render={({ field }) => (
              <div className="flex items-start justify-between gap-4 border-t border-border pt-3">
                <div>
                  <label htmlFor="s-active" className="text-xs font-medium">
                    Active
                  </label>
                  <p className="text-xs text-fg-subtle">
                    {stdio ? "Workers start this command and keep it connected. You confirm the command when saving." : "Workers connect to this server and keep the connection healthy."}
                  </p>
                  {stdio && server?.command_confirmed_at ? (
                    <p className="text-xs text-fg-subtle">Command last confirmed {dateTime(server.command_confirmed_at)}.</p>
                  ) : null}
                </div>
                <Switch id="s-active" checked={field.value} onCheckedChange={field.onChange} aria-label="Server active" />
              </div>
            )}
          />
        </div>

        {formError ? (
          <p role="alert" className="rounded-md bg-danger-bg px-3 py-2 text-sm text-danger">
            {formError}
          </p>
        ) : null}
      </form>

      <CommandConfirm values={confirming} pending={create.isPending || update.isPending} onCancel={() => setConfirming(null)} onConfirm={(v) => void save(v, true)} />
    </>
  );
}

function CommandConfirm({
  values,
  pending,
  onCancel,
  onConfirm,
}: {
  values: ServerFormValues | null;
  pending: boolean;
  onCancel: () => void;
  onConfirm: (v: ServerFormValues) => void;
}) {
  const [last, setLast] = React.useState(values);
  if (values && values !== last) setLast(values);
  const v = values ?? last;
  const envNames = v ? v.env.filter((r) => !(r.existing && r.mode === "remove") && r.name.trim()).map((r) => r.name.trim()) : [];
  return (
    <Modal
      open={!!values}
      onOpenChange={(o) => !o && onCancel()}
      title="Confirm the command"
      description="This runs on the worker host with the worker's permissions."
      footer={
        <>
          <Button variant="ghost" onClick={onCancel}>
            Back to editing
          </Button>
          <Button variant="primary" loading={pending} onClick={() => v && onConfirm(v)}>
            <TerminalSquare /> Confirm and activate
          </Button>
        </>
      }
    >
      {v ? (
        <div className="flex flex-col gap-3 text-sm">
          <p className="text-fg-muted">Workers will start exactly this process. Check every argument before you activate it.</p>
          <pre
            aria-label="Command line"
            className="scrollbar-thin overflow-x-auto whitespace-pre-wrap break-all rounded-md border border-border-strong bg-subtle px-3 py-2 font-mono text-xs text-fg"
          >
            {commandLine(v.command.trim(), parseArgs(v.args))}
          </pre>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-xs">
            <dt className="text-fg-muted">Working directory</dt>
            <dd className="font-mono">{v.cwd.trim() || "Worker default"}</dd>
            <dt className="text-fg-muted">Environment</dt>
            <dd className="font-mono">{envNames.length ? envNames.join(", ") : "None (only the variables listed here are passed)"}</dd>
          </dl>
        </div>
      ) : null}
    </Modal>
  );
}
