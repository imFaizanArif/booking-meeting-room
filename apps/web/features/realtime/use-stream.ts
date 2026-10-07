"use client";

import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { api, unwrap, type Schemas } from "@/lib/api/client";

type ExecutionEvent = Schemas["ExecutionEventOut"];

async function token(): Promise<string> {
  return (await unwrap(await api.POST("/api/v1/realtime/token"))).token;
}

export type StreamState = "connecting" | "live" | "reconnecting" | "closed";

/**
 * Live execution events over SSE with gap-free replay. Reconnects with a fresh token and
 * resumes after the last sequence number seen.
 */
export function useExecutionStream(executionId: string | undefined, onEvent: (event: ExecutionEvent) => void, enabled = true) {
  const [state, setState] = React.useState<StreamState>("connecting");
  const lastSeq = React.useRef(0);
  const handler = React.useRef(onEvent);
  React.useLayoutEffect(() => {
    handler.current = onEvent;
  });

  React.useEffect(() => {
    if (!executionId || !enabled) return;
    let source: EventSource | null = null;
    let stopped = false;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function open() {
      try {
        const t = await token();
        if (stopped) return;
        source = new EventSource(`/api/v1/realtime/executions/${executionId}?token=${encodeURIComponent(t)}&after_seq=${lastSeq.current}`);
        source.onopen = () => {
          retry = 0;
          setState("live");
        };
        source.onmessage = () => undefined;
        source.onerror = () => {
          source?.close();
          if (stopped) return;
          setState("reconnecting");
          retry += 1;
          timer = setTimeout(open, Math.min(10_000, 500 * 2 ** retry));
        };
        const listener = (e: MessageEvent<string>) => {
          const event = JSON.parse(e.data) as ExecutionEvent;
          if (event.seq <= lastSeq.current) return;
          lastSeq.current = event.seq;
          handler.current(event);
        };
        for (const type of EVENT_TYPES) source.addEventListener(type, listener as EventListener);
      } catch {
        if (!stopped) {
          setState("reconnecting");
          timer = setTimeout(open, 2000);
        }
      }
    }
    void open();
    return () => {
      stopped = true;
      clearTimeout(timer);
      source?.close();
      setState("closed");
    };
  }, [executionId, enabled]);

  return { state };
}

/** Workspace-level notifications: invalidate the relevant queries when something changes. */
export function useWorkspaceStream() {
  const qc = useQueryClient();
  React.useEffect(() => {
    let source: EventSource | null = null;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function open() {
      try {
        const t = await token();
        if (stopped) return;
        source = new EventSource(`/api/v1/realtime/workspace?token=${encodeURIComponent(t)}`);
        const invalidate = (keys: string[][]) => keys.forEach((k) => void qc.invalidateQueries({ queryKey: k }));
        source.addEventListener("approval.created", () => invalidate([["approvals"], ["dashboard"]]));
        source.addEventListener("approval.decided", () => invalidate([["approvals"], ["dashboard"]]));
        for (const t of ["execution.created", "execution.started", "execution.paused", "execution.resumed", "execution.completed", "execution.failed", "execution.cancelled"]) {
          source.addEventListener(t, () => invalidate([["executions"], ["dashboard"]]));
        }
        source.addEventListener("mcp.server_status_changed", () => invalidate([["mcp"], ["dashboard"]]));
        source.onerror = () => {
          source?.close();
          if (!stopped) timer = setTimeout(open, 5000);
        };
      } catch {
        if (!stopped) timer = setTimeout(open, 5000);
      }
    }
    void open();
    return () => {
      stopped = true;
      clearTimeout(timer);
      source?.close();
    };
  }, [qc]);
}

export const EVENT_TYPES = [
  "execution.created", "execution.started", "execution.paused", "execution.resumed", "execution.completed",
  "execution.failed", "execution.cancelled", "node.started", "node.completed", "node.failed", "node.retrying",
  "llm.requested", "llm.completed", "tool.requested", "tool.awaiting_approval", "tool.approved", "tool.rejected",
  "tool.executing", "tool.completed", "tool.failed", "approval.created", "approval.decided", "mcp.server_status_changed",
] as const;
