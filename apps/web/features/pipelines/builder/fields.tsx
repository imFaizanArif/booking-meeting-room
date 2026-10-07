"use client";

import * as React from "react";

import { CodeEditor } from "@/components/ui/code-editor";

/** JSON editor bound to a value. Keeps the text while it does not parse; empty means null when allowed. */
export function JsonCodeField({
  value,
  onChange,
  ariaLabel,
  nullable,
  invalid,
  minHeight = "72px",
  maxHeight = "320px",
}: {
  value: unknown;
  onChange: (value: unknown) => void;
  ariaLabel: string;
  nullable?: boolean;
  invalid?: boolean;
  minHeight?: string;
  maxHeight?: string;
}) {
  const format = (v: unknown) => (v === null || v === undefined ? (nullable ? "" : "{}") : JSON.stringify(v, null, 2));
  const [text, setText] = React.useState(() => format(value));
  const [error, setError] = React.useState<string | null>(null);
  const last = React.useRef<unknown>(value);

  // Follow external changes (restore, reload) without clobbering an in-progress edit.
  React.useEffect(() => {
    if (value !== last.current) {
      last.current = value;
      setText(format(value));
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <div className="flex flex-col gap-1">
      <CodeEditor
        ariaLabel={ariaLabel}
        value={text}
        language="json"
        minHeight={minHeight}
        maxHeight={maxHeight}
        invalid={invalid || !!error}
        onChange={(next) => {
          setText(next);
          if (!next.trim() && nullable) {
            setError(null);
            last.current = null;
            onChange(null);
            return;
          }
          try {
            const parsed: unknown = JSON.parse(next);
            setError(null);
            last.current = parsed;
            onChange(parsed);
          } catch (e) {
            setError(e instanceof Error ? `Not valid JSON yet: ${e.message}` : "Not valid JSON yet");
          }
        }}
      />
      {error ? <span className="text-xs text-warn">{error}</span> : null}
    </div>
  );
}

export function TemplateField({ value, onChange, completions, ariaLabel, invalid, minHeight = "88px" }: {
  value: string;
  onChange: (value: string) => void;
  completions: string[];
  ariaLabel: string;
  invalid?: boolean;
  minHeight?: string;
}) {
  return <CodeEditor language="template" value={value} onChange={onChange} completions={completions} ariaLabel={ariaLabel} invalid={invalid} minHeight={minHeight} maxHeight="360px" />;
}
