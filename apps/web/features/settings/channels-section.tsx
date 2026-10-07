"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { BellRing, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/menus";
import { ConfirmDialog, Drawer } from "@/components/ui/overlay";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Checkbox, Switch } from "@/components/ui/toggles";
import { applyServerErrors, FormError } from "@/components/ui-extra/form-error";
import { SegmentedControl } from "@/components/ui-extra/segmented";
import { ApiError, type Schemas } from "@/lib/api/client";
import { dateTime, relativeTime } from "@/lib/format";

import { maskHint } from "./format";
import { useDeleteChannel, useSaveChannel } from "./mutations";
import { CHANNEL_EVENTS, useChannels } from "./queries";
import { ReadOnlyNote, SettingsSection } from "./section";

type Channel = Schemas["ChannelOut"];
type ChannelType = Schemas["NotificationChannelType"];

const TYPE_LABEL: Record<ChannelType, string> = { webhook: "Webhook", slack: "Slack", discord: "Discord" };
const URL_PLACEHOLDER: Record<ChannelType, string> = {
  webhook: "https://example.com/hooks/agent-platform",
  slack: "https://hooks.slack.com/services/…",
  discord: "https://discord.com/api/webhooks/…",
};

export const channelSchema = z
  .object({
    name: z.string().trim().min(1, "Give the channel a name").max(200, "200 characters at most"),
    channel_type: z.enum(["webhook", "slack", "discord"]),
    url_required: z.boolean(),
    url: z.string(),
    signing_secret: z.string(),
    events: z.array(z.string()),
    is_active: z.boolean(),
  })
  .superRefine((v, ctx) => {
    const url = v.url.trim();
    if (v.url_required && !url) ctx.addIssue({ code: "custom", path: ["url"], message: "Paste the incoming webhook URL" });
    else if (url && !/^https?:\/\/\S+$/i.test(url)) ctx.addIssue({ code: "custom", path: ["url"], message: "Use a full http(s) URL" });
    if (v.events.length === 0) ctx.addIssue({ code: "custom", path: ["events"], message: "Pick at least one event" });
  });
type ChannelValues = z.infer<typeof channelSchema>;

function ChannelForm({ channel, save, onDone }: { channel: Channel | null; save: ReturnType<typeof useSaveChannel>; onDone: () => void }) {
  const [replaceUrl, setReplaceUrl] = React.useState(!channel?.url.is_set);
  const [replaceSecret, setReplaceSecret] = React.useState(!channel?.signing_secret.is_set);
  const [error, setError] = React.useState<unknown>(null);
  const form = useForm<ChannelValues>({
    resolver: zodResolver(channelSchema),
    defaultValues: {
      name: channel?.name ?? "",
      channel_type: channel?.channel_type ?? "slack",
      url_required: !channel?.url.is_set,
      url: "",
      signing_secret: "",
      events: channel?.events.length ? channel.events : ["approval.created"],
      is_active: channel?.is_active ?? true,
    },
  });
  const { errors } = form.formState;
  const type = form.watch("channel_type");
  const events = form.watch("events");
  const knownEvents = [...CHANNEL_EVENTS.map((e) => e.value as string), ...events.filter((e) => !CHANNEL_EVENTS.some((k) => k.value === e))];

  async function onSubmit(v: ChannelValues) {
    setError(null);
    const body: Schemas["ChannelIn"] = {
      name: v.name.trim(),
      channel_type: v.channel_type,
      events: v.events,
      is_active: v.is_active,
      url: replaceUrl && v.url.trim() ? v.url.trim() : null,
      signing_secret: v.channel_type === "webhook" && replaceSecret && v.signing_secret ? v.signing_secret : null,
    };
    try {
      const saved = await save.mutateAsync({ id: channel?.id, body });
      toast.success(channel ? `Saved ${saved.name}` : `Added ${saved.name}`);
      onDone();
    } catch (err) {
      const leftover = applyServerErrors(err, form.setError, ["name", "channel_type", "url", "signing_secret", "events", "is_active"]);
      if (!(err instanceof ApiError && err.fields.length && !leftover.length)) setError(err);
    }
  }

  return (
    <form id="channel-form" onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <span id="c-type-label" className="text-xs font-medium">
          Type
        </span>
        <Controller
          control={form.control}
          name="channel_type"
          render={({ field }) => (
            <SegmentedControl
              aria-labelledby="c-type-label"
              className="self-start"
              value={field.value}
              onValueChange={field.onChange}
              options={[
                { value: "slack", label: "Slack" },
                { value: "discord", label: "Discord" },
                { value: "webhook", label: "Webhook" },
              ]}
            />
          )}
        />
      </div>

      <Field label="Name" htmlFor="c-name" required error={errors.name?.message}>
        <Input id="c-name" autoComplete="off" placeholder="#ops-approvals" aria-invalid={!!errors.name} {...form.register("name")} />
      </Field>

      <Field
        label={type === "webhook" ? "Endpoint URL" : "Incoming webhook URL"}
        htmlFor="c-url"
        required={!channel?.url.is_set}
        error={errors.url?.message}
        hint={replaceUrl ? "Write-only. Stored encrypted and never shown again." : undefined}
      >
        {replaceUrl ? (
          <div className="flex gap-2">
            <Input
              id="c-url"
              type="url"
              autoComplete="off"
              spellCheck={false}
              className="font-mono text-xs"
              placeholder={URL_PLACEHOLDER[type]}
              aria-invalid={!!errors.url}
              {...form.register("url")}
            />
            {channel?.url.is_set ? (
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setReplaceUrl(false);
                  form.setValue("url", "");
                  form.clearErrors("url");
                }}
              >
                Keep current
              </Button>
            ) : null}
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs text-fg-muted">Set · {maskHint(channel?.url.hint)}</span>
            <Button type="button" size="sm" onClick={() => setReplaceUrl(true)}>
              Replace URL
            </Button>
          </div>
        )}
      </Field>

      {type === "webhook" ? (
        <Field
          label="Signing secret"
          htmlFor="c-secret"
          error={errors.signing_secret?.message}
          hint={replaceSecret ? <>Optional. Each request carries an <span className="font-mono">x-agent-platform-signature</span> header, an HMAC-SHA256 of the timestamp and body.</> : undefined}
        >
          {replaceSecret ? (
            <div className="flex gap-2">
              <Input id="c-secret" type="password" autoComplete="new-password" className="font-mono text-xs" aria-invalid={!!errors.signing_secret} {...form.register("signing_secret")} />
              {channel?.signing_secret.is_set ? (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setReplaceSecret(false);
                    form.setValue("signing_secret", "");
                  }}
                >
                  Keep current
                </Button>
              ) : null}
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs text-fg-muted">Set · {maskHint(channel?.signing_secret.hint)}</span>
              <Button type="button" size="sm" onClick={() => setReplaceSecret(true)}>
                Replace secret
              </Button>
            </div>
          )}
        </Field>
      ) : null}

      <fieldset className="flex flex-col gap-1.5">
        <legend className="mb-1 text-xs font-medium">Events</legend>
        <Controller
          control={form.control}
          name="events"
          render={({ field }) => (
            <div className="flex flex-col divide-y divide-border rounded-md border border-border">
              {knownEvents.map((value) => {
                const meta = CHANNEL_EVENTS.find((e) => e.value === value);
                const id = `c-ev-${value.replace(/\W/g, "-")}`;
                const checked = field.value.includes(value);
                return (
                  <label key={value} htmlFor={id} className="flex cursor-pointer items-start gap-2.5 px-3 py-2 hover:bg-subtle">
                    <Checkbox
                      id={id}
                      className="mt-0.5"
                      checked={checked}
                      onCheckedChange={(c) => field.onChange(c ? [...field.value, value] : field.value.filter((x) => x !== value))}
                    />
                    <span className="min-w-0">
                      <span className="block text-sm">{meta?.label ?? value}</span>
                      <span className="block text-xs text-fg-muted">
                        <span className="font-mono">{value}</span>
                        {meta ? ` · ${meta.description}` : null}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          )}
        />
        {errors.events ? (
          <p role="alert" className="text-xs text-danger">
            {errors.events.message}
          </p>
        ) : null}
      </fieldset>

      <div className="flex items-start justify-between gap-4 border-t border-border pt-4">
        <div>
          <label htmlFor="c-active" className="text-xs font-medium">
            Active
          </label>
          <p className="text-xs text-fg-subtle">Inactive channels keep their settings but receive nothing.</p>
        </div>
        <Controller control={form.control} name="is_active" render={({ field }) => <Switch id="c-active" checked={field.value} onCheckedChange={field.onChange} />} />
      </div>
      <FormError error={error} />
    </form>
  );
}

function ChannelDrawer({ open, onOpenChange, channel }: { open: boolean; onOpenChange: (open: boolean) => void; channel: Channel | null }) {
  const save = useSaveChannel();
  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title={channel ? "Edit channel" : "Add channel"}
      description={channel ? channel.name : "Send approval requests and pipeline notifications to Slack, Discord or any HTTPS endpoint."}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" form="channel-form" variant="primary" loading={save.isPending}>
            Save channel
          </Button>
        </>
      }
    >
      {open ? <ChannelForm key={channel?.id ?? "new"} channel={channel} save={save} onDone={() => onOpenChange(false)} /> : null}
    </Drawer>
  );
}

function Delivery({ channel }: { channel: Channel }) {
  if (channel.last_delivery_ok == null) return <span className="text-fg-subtle">No deliveries yet</span>;
  return (
    <span className="inline-flex items-center gap-1.5" title={dateTime(channel.last_delivery_at)}>
      <Badge tone={channel.last_delivery_ok ? "ok" : "danger"}>{channel.last_delivery_ok ? "Delivered" : "Failed"}</Badge>
      <span className="text-xs text-fg-muted">{relativeTime(channel.last_delivery_at)}</span>
    </span>
  );
}

export function ChannelsSection({ isOwner }: { isOwner: boolean }) {
  const channels = useChannels();
  const remove = useDeleteChannel();
  const [editing, setEditing] = React.useState<Channel | null>(null);
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [deleting, setDeleting] = React.useState<Channel | null>(null);

  function openCreate() {
    setEditing(null);
    setDrawerOpen(true);
  }

  return (
    <SettingsSection
      id="channels"
      title="Notification channels"
      description="Where the platform posts when something needs a person. URLs and signing secrets are write-only."
      actions={
        isOwner && channels.data?.length ? (
          <Button size="sm" onClick={openCreate}>
            <Plus /> Add channel
          </Button>
        ) : null
      }
    >
      {channels.isPending ? (
        <LoadingState rows={2} />
      ) : channels.error ? (
        <ErrorState error={channels.error} onRetry={() => void channels.refetch()} />
      ) : channels.data.length === 0 ? (
        <EmptyState
          icon={BellRing}
          title="No notification channels"
          body="Add a Slack, Discord or webhook channel to hear about approvals without keeping the console open."
          action={
            isOwner ? (
              <Button size="sm" onClick={openCreate}>
                <Plus /> Add channel
              </Button>
            ) : undefined
          }
        />
      ) : (
        <DataTable
          rows={channels.data}
          getRowId={(c) => c.id}
          onRowClick={
            isOwner
              ? (c) => {
                  setEditing(c);
                  setDrawerOpen(true);
                }
              : undefined
          }
          columns={[
            { id: "name", header: "Name", sortValue: (c) => c.name.toLowerCase(), cell: (c) => <span className="font-medium">{c.name}</span> },
            { id: "type", header: "Type", cell: (c) => <span className="text-fg-muted">{TYPE_LABEL[c.channel_type]}</span> },
            {
              id: "events",
              header: "Events",
              cell: (c) => (
                <div className="flex flex-wrap gap-1">
                  {c.events.length ? (
                    c.events.map((e) => (
                      <Badge key={e} tone="outline" className="font-mono">
                        {e}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-xs text-fg-subtle">All events</span>
                  )}
                </div>
              ),
            },
            { id: "active", header: "Active", cell: (c) => (c.is_active ? <span>Active</span> : <span className="text-fg-subtle">Off</span>) },
            { id: "delivery", header: "Last delivery", cell: (c) => <Delivery channel={c} /> },
            {
              id: "actions",
              header: <span className="sr-only">Actions</span>,
              align: "right",
              cell: (c) =>
                isOwner ? (
                  <div onClick={(e) => e.stopPropagation()}>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button size="icon" variant="ghost" aria-label={`Actions for ${c.name}`}>
                          <MoreHorizontal />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent>
                        <DropdownMenuItem
                          onSelect={() => {
                            setEditing(c);
                            setDrawerOpen(true);
                          }}
                        >
                          <Pencil /> Edit channel
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem tone="danger" onSelect={() => setDeleting(c)}>
                          <Trash2 /> Delete channel
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                ) : null,
            },
          ]}
        />
      )}
      {!isOwner ? <ReadOnlyNote>Only owners can add or change notification channels.</ReadOnlyNote> : null}
      {isOwner ? <ChannelDrawer open={drawerOpen} onOpenChange={setDrawerOpen} channel={editing} /> : null}
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="Delete channel"
        tone="danger"
        confirmLabel="Delete channel"
        loading={remove.isPending}
        body={
          <>
            <span className="font-medium text-fg">{deleting?.name}</span> stops receiving notifications and its stored URL and signing secret are deleted.
          </>
        }
        onConfirm={() => deleting && remove.mutate(deleting.id, { onSuccess: () => setDeleting(null) })}
      />
    </SettingsSection>
  );
}
