"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { UserPlus } from "lucide-react";
import * as React from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/overlay";
import { Select } from "@/components/ui/select";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { applyServerErrors, FormError } from "@/components/ui-extra/form-error";
import { ApiError, type Schemas } from "@/lib/api/client";
import { dateTime, relativeTime } from "@/lib/format";

import { useAddMember, useUpdateMemberRole } from "./mutations";
import { useMembers } from "./queries";
import { ReadOnlyNote, SettingsSection } from "./section";

type Role = Schemas["Role"];

export const ROLES: { value: Role; label: string; description: string }[] = [
  { value: "owner", label: "Owner", description: "Everything, including members, channels and secrets." },
  { value: "operator", label: "Operator", description: "Run pipelines, decide approvals, edit configuration." },
  { value: "viewer", label: "Viewer", description: "Read-only access." },
];

const LAST_OWNER = "A workspace needs at least one owner.";

export const memberSchema = z.object({
  email: z.string().trim().regex(/^[^@\s]+@[^@\s]+$/, "Enter a valid email"),
  display_name: z.string().trim().min(1, "Enter a name").max(200, "200 characters at most"),
  role: z.enum(["owner", "operator", "viewer"]),
  password: z.string().min(12, "At least 12 characters").max(200, "200 characters at most"),
});
type MemberValues = z.infer<typeof memberSchema>;

function AddMemberModal({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const add = useAddMember();
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title="Add member"
      description="They sign in with this email and the initial password. Share the password out of band."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" form="add-member-form" variant="primary" loading={add.isPending}>
            Add member
          </Button>
        </>
      }
    >
      {open ? <AddMemberForm add={add} onDone={() => onOpenChange(false)} /> : null}
    </Modal>
  );
}

function AddMemberForm({ add, onDone }: { add: ReturnType<typeof useAddMember>; onDone: () => void }) {
  const [error, setError] = React.useState<unknown>(null);
  const form = useForm<MemberValues>({
    resolver: zodResolver(memberSchema),
    defaultValues: { email: "", display_name: "", role: "operator", password: "" },
  });
  const { errors } = form.formState;

  async function onSubmit(values: MemberValues) {
    setError(null);
    try {
      const member = await add.mutateAsync({ ...values, email: values.email.trim(), display_name: values.display_name.trim() });
      toast.success(`${member.email} added as ${member.role}`);
      onDone();
    } catch (err) {
      const leftover = applyServerErrors(err, form.setError, ["email", "display_name", "role", "password"]);
      if (!(err instanceof ApiError && err.fields.length && !leftover.length)) setError(err);
    }
  }

  return (
    <form id="add-member-form" onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex flex-col gap-3">
      <Field label="Email" htmlFor="m-email" required error={errors.email?.message}>
        <Input id="m-email" type="email" autoComplete="off" autoFocus aria-invalid={!!errors.email} {...form.register("email")} />
      </Field>
      <Field label="Name" htmlFor="m-name" required error={errors.display_name?.message}>
        <Input id="m-name" autoComplete="off" aria-invalid={!!errors.display_name} {...form.register("display_name")} />
      </Field>
      <Field label="Role" htmlFor="m-role" required error={errors.role?.message}>
        <Controller
          control={form.control}
          name="role"
          render={({ field }) => <Select id="m-role" value={field.value} onValueChange={field.onChange} options={ROLES} />}
        />
      </Field>
      <Field label="Initial password" htmlFor="m-password" required error={errors.password?.message} hint="At least 12 characters.">
        <Input id="m-password" type="password" autoComplete="new-password" aria-invalid={!!errors.password} {...form.register("password")} />
      </Field>
      <FormError error={error} />
    </form>
  );
}

export function MembersSection({ isOwner, currentUserId }: { isOwner: boolean; currentUserId: string | undefined }) {
  const members = useMembers();
  const updateRole = useUpdateMemberRole();
  const [adding, setAdding] = React.useState(false);
  const ownerCount = members.data?.filter((m) => m.role === "owner").length ?? 0;

  return (
    <SettingsSection
      id="members"
      title="Members and roles"
      description="Everyone with access to this workspace. Roles decide what they can change; the API enforces them."
      actions={
        isOwner ? (
          <Button size="sm" onClick={() => setAdding(true)}>
            <UserPlus /> Add member
          </Button>
        ) : null
      }
    >
      {members.isPending ? (
        <LoadingState rows={3} />
      ) : members.error ? (
        <ErrorState error={members.error} onRetry={() => void members.refetch()} />
      ) : (
        <DataTable
          rows={members.data}
          getRowId={(m) => m.user_id}
          empty="No members."
          columns={[
            {
              id: "email",
              header: "Email",
              sortValue: (m) => m.email,
              cell: (m) => (
                <span className="font-medium">
                  {m.email}
                  {m.user_id === currentUserId ? <span className="ml-1.5 text-xs font-normal text-fg-subtle">(you)</span> : null}
                </span>
              ),
            },
            { id: "name", header: "Name", sortValue: (m) => m.display_name, cell: (m) => <span className="text-fg-muted">{m.display_name}</span> },
            {
              id: "role",
              header: "Role",
              cell: (m) => {
                if (!isOwner) return <Badge tone={m.role === "owner" ? "outline" : "neutral"}>{ROLES.find((r) => r.value === m.role)?.label ?? m.role}</Badge>;
                const lastOwner = m.role === "owner" && ownerCount <= 1;
                return (
                  <Select
                    size="sm"
                    className="w-32"
                    value={m.role}
                    disabled={updateRole.isPending && updateRole.variables?.userId === m.user_id}
                    onValueChange={(role) => {
                      if (role === m.role) return;
                      updateRole.mutate(
                        { userId: m.user_id, role: role as Role },
                        { onSuccess: (out) => toast.success(`${out.email} is now ${out.role}`) },
                      );
                    }}
                    options={ROLES.map((r) => ({
                      value: r.value,
                      label: r.label,
                      disabled: lastOwner && r.value !== "owner",
                      description: lastOwner && r.value !== "owner" ? LAST_OWNER : undefined,
                    }))}
                  />
                );
              },
            },
            {
              id: "login",
              header: "Last sign-in",
              sortValue: (m) => m.last_login_at ?? "",
              cell: (m) =>
                m.last_login_at ? (
                  <span className="text-fg-muted tabular" title={dateTime(m.last_login_at)}>
                    {relativeTime(m.last_login_at)}
                  </span>
                ) : (
                  <span className="text-fg-subtle">Never</span>
                ),
            },
          ]}
        />
      )}
      {updateRole.error ? <FormError error={updateRole.error} /> : null}
      {!isOwner ? <ReadOnlyNote>Only owners can add members or change roles.</ReadOnlyNote> : null}
      {isOwner ? <AddMemberModal open={adding} onOpenChange={setAdding} /> : null}
    </SettingsSection>
  );
}
