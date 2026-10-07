"use client";

import * as React from "react";

import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

import { COMMON_TIMEZONES } from "./describe";

const CUSTOM = "__custom__";

/** Common IANA zones in a select, with "Other" switching to a free-text input. */
export function TimezoneField({ id, value, onChange, invalid }: { id: string; value: string; onChange: (value: string) => void; invalid?: boolean }) {
  const known = (COMMON_TIMEZONES as readonly string[]).includes(value);
  const [custom, setCustom] = React.useState(!known && value !== "");
  const browserZone = React.useMemo(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone;
    } catch {
      return undefined;
    }
  }, []);

  const options = [
    ...COMMON_TIMEZONES.map((z) => ({ value: z as string, label: z === browserZone ? `${z} (your timezone)` : z })),
    { value: CUSTOM, label: "Other IANA name…" },
  ];

  return (
    <div className="flex flex-col gap-2">
      <Select
        id={id}
        aria-invalid={invalid && !custom}
        value={custom ? CUSTOM : known ? value : undefined}
        placeholder="Choose a timezone"
        options={options}
        onValueChange={(v) => {
          if (v === CUSTOM) {
            setCustom(true);
            return;
          }
          setCustom(false);
          onChange(v);
        }}
      />
      {custom ? (
        <Input
          id={`${id}-custom`}
          aria-label="IANA timezone name"
          aria-invalid={invalid}
          className="font-mono text-xs"
          placeholder="America/Argentina/Buenos_Aires"
          value={value}
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => onChange(e.target.value.trim())}
        />
      ) : null}
    </div>
  );
}
