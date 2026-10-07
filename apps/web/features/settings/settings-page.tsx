"use client";

import * as React from "react";

import { PageContainer } from "@/components/shell/page-container";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page";
import { canOperate, useMe } from "@/features/auth/queries";
import { cn } from "@/lib/utils";

import { ChannelsSection } from "./channels-section";
import { MembersSection } from "./members-section";
import { SecretsSection } from "./secrets-section";
import { VariablesSection } from "./variables-section";
import { WorkspaceSection } from "./workspace-section";

const SECTIONS = [
  { id: "workspace", label: "Workspace" },
  { id: "members", label: "Members and roles" },
  { id: "channels", label: "Notification channels" },
  { id: "variables", label: "Prompt variables" },
  { id: "secrets", label: "Secrets", ownerOnly: true },
] as const;

/** Highlights the section nearest the top of the scroll container. */
function useActiveSection(ids: readonly string[]) {
  const [active, setActive] = React.useState<string>(ids[0]!);
  React.useEffect(() => {
    const els = ids.map((id) => document.getElementById(id)).filter((el): el is HTMLElement => !!el);
    if (!els.length || typeof IntersectionObserver === "undefined") return;
    const visible = new Map<string, boolean>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) visible.set(e.target.id, e.isIntersecting);
        const first = ids.find((id) => visible.get(id));
        if (first) setActive(first);
      },
      { rootMargin: "0px 0px -65% 0px" },
    );
    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [ids]);
  return [active, setActive] as const;
}

export function SettingsPage() {
  const me = useMe();
  const role = me.data?.role;
  const isOwner = role === "owner";
  const ids = React.useMemo(() => SECTIONS.map((s) => s.id), []);
  const [active, setActive] = useActiveSection(ids);

  // Honour deep links such as /settings#variables once the sections have rendered.
  React.useEffect(() => {
    const hash = window.location.hash.slice(1);
    if (hash && ids.includes(hash as (typeof ids)[number])) document.getElementById(hash)?.scrollIntoView({ block: "start" });
  }, [ids]);

  return (
    <PageContainer>
      <PageHeader
        title="Settings"
        description="Workspace, people, notifications and the shared values pipelines use."
        meta={
          role ? (
            <span className="inline-flex items-center gap-1.5">
              Your role <Badge tone="outline">{role[0]!.toUpperCase() + role.slice(1)}</Badge>
              {!isOwner ? <span className="text-fg-subtle">Some sections are read-only for you.</span> : null}
            </span>
          ) : null
        }
      />
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[180px_minmax(0,1fr)]">
        <nav aria-label="Settings sections" className="hidden lg:block">
          <ul className="sticky top-6 flex flex-col gap-0.5 border-l border-border">
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <a
                  href={`#${s.id}`}
                  onClick={() => setActive(s.id)}
                  aria-current={active === s.id ? "location" : undefined}
                  className={cn(
                    "-ml-px flex items-center justify-between border-l-2 border-transparent py-1 pl-3 pr-2 text-sm text-fg-muted hover:text-fg",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25",
                    active === s.id && "border-fg font-medium text-fg",
                  )}
                >
                  {s.label}
                  {"ownerOnly" in s && s.ownerOnly && !isOwner ? <span className="text-2xs text-fg-subtle">Owner</span> : null}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="flex min-w-0 flex-col gap-8">
          <WorkspaceSection isOwner={isOwner} />
          <MembersSection isOwner={isOwner} currentUserId={me.data?.user_id} />
          <ChannelsSection isOwner={isOwner} />
          <VariablesSection canEdit={canOperate(role)} />
          <SecretsSection isOwner={isOwner} />
        </div>
      </div>
    </PageContainer>
  );
}
