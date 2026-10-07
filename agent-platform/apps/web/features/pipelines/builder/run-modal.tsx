"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { CodeEditor } from "@/components/ui/code-editor";
import { Field } from "@/components/ui/field";
import { Modal } from "@/components/ui/overlay";
import { ApiError } from "@/lib/api/client";

import { useRunPipeline } from "../mutations";

export function RunModal({ open, onOpenChange, pipelineId, defaults, dirty, version }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pipelineId: string;
  defaults: Record<string, unknown>;
  dirty: boolean;
  version: number;
}) {
  const router = useRouter();
  const run = useRunPipeline(pipelineId);
  const [text, setText] = React.useState(() => JSON.stringify(defaults, null, 2));
  const [errors, setErrors] = React.useState<string[]>([]);
  const [wasOpen, setWasOpen] = React.useState(open);
  if (wasOpen !== open) {
    setWasOpen(open);
    if (open) {
      setText(JSON.stringify(defaults, null, 2));
      setErrors([]);
    }
  }

  let parsed: Record<string, unknown> | null = null;
  try {
    const value: unknown = JSON.parse(text);
    parsed = value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
  } catch {
    parsed = null;
  }

  async function start() {
    if (!parsed) return;
    setErrors([]);
    try {
      const execution = await run.mutateAsync(parsed);
      toast.success("Execution started.");
      onOpenChange(false);
      router.push(`/executions/${execution.id}`);
    } catch (e) {
      if (e instanceof ApiError) setErrors(e.fields.length ? e.fields.map((f) => `${f.field || "input"}: ${f.message}`) : [e.message]);
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={`Run version ${version}`}
      description={dirty ? "You have unsaved changes. The run uses the last saved version." : "The input is validated against the trigger's input schema."}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" onClick={() => void start()} loading={run.isPending} disabled={!parsed}>
            Start execution
          </Button>
        </>
      }
    >
      <Field label="Input (JSON)" htmlFor="run-input" error={!parsed ? "Input must be a JSON object" : null}>
        <CodeEditor value={text} onChange={setText} minHeight="160px" ariaLabel="Run input" invalid={!parsed || errors.length > 0} />
      </Field>
      {errors.length ? (
        <ul role="alert" className="mt-2 flex flex-col gap-0.5 text-xs text-danger">
          {errors.map((e) => <li key={e}>{e}</li>)}
        </ul>
      ) : null}
    </Modal>
  );
}
