"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

import { CodeEditor } from "./code-editor";
import { Field } from "./field";
import { Input, Textarea } from "./input";
import { Select } from "./select";
import { Switch } from "./toggles";

export type JsonSchema = {
  type?: string | string[];
  title?: string;
  description?: string;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  items?: JsonSchema;
  enum?: unknown[];
  const?: unknown;
  default?: unknown;
  anyOf?: JsonSchema[];
  oneOf?: JsonSchema[];
  allOf?: JsonSchema[];
  $ref?: string;
  $defs?: Record<string, JsonSchema>;
  additionalProperties?: boolean | JsonSchema;
  minimum?: number;
  maximum?: number;
  format?: string;
};

export type FieldOverride = (args: {
  path: string;
  schema: JsonSchema;
  value: unknown;
  onChange: (value: unknown) => void;
  error?: string;
}) => React.ReactNode | undefined;

interface Props {
  schema: JsonSchema;
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
  errors?: Record<string, string>;
  override?: FieldOverride;
  hidden?: string[];
  idPrefix?: string;
}

function resolve(schema: JsonSchema, root: JsonSchema): JsonSchema {
  let current = schema;
  for (let guard = 0; guard < 8; guard++) {
    if (current.$ref) {
      const name = current.$ref.split("/").pop() ?? "";
      const target = root.$defs?.[name];
      if (!target) return current;
      current = { ...target, ...Object.fromEntries(Object.entries(current).filter(([k]) => k !== "$ref")) };
      continue;
    }
    if (current.allOf?.length === 1) {
      current = { ...resolve(current.allOf[0]!, root), title: current.title, description: current.description, default: current.default };
      continue;
    }
    const variants = current.anyOf ?? current.oneOf;
    if (variants) {
      const nonNull = variants.filter((v) => v.type !== "null");
      if (nonNull.length === 1) {
        current = { ...resolve(nonNull[0]!, root), title: current.title, description: current.description, default: current.default };
        continue;
      }
    }
    return current;
  }
  return current;
}

function primaryType(schema: JsonSchema): string | undefined {
  return Array.isArray(schema.type) ? schema.type.find((t) => t !== "null") : schema.type;
}

function humanLabel(key: string, schema: JsonSchema): string {
  if (schema.title && schema.title.toLowerCase() !== key.replace(/_/g, " ")) return schema.title;
  const text = key.replace(/_/g, " ");
  return text[0]!.toUpperCase() + text.slice(1);
}

function JsonField({ id, value, onChange, invalid }: { id: string; value: unknown; onChange: (v: unknown) => void; invalid?: boolean }) {
  const [text, setText] = React.useState(() => JSON.stringify(value ?? null, null, 2));
  const [parseError, setParseError] = React.useState<string | null>(null);
  return (
    <div className="flex flex-col gap-1">
      <CodeEditor
        ariaLabel={id}
        value={text}
        minHeight="72px"
        maxHeight="320px"
        invalid={invalid || !!parseError}
        onChange={(next) => {
          setText(next);
          try {
            onChange(JSON.parse(next));
            setParseError(null);
          } catch {
            setParseError("Not valid JSON yet");
          }
        }}
      />
      {parseError ? <span className="text-xs text-warn">{parseError}</span> : null}
    </div>
  );
}

function SchemaField({ path, name, schema, root, value, onChange, errors, override, required, idPrefix }: {
  path: string;
  name: string;
  schema: JsonSchema;
  root: JsonSchema;
  value: unknown;
  onChange: (value: unknown) => void;
  errors?: Record<string, string>;
  override?: FieldOverride;
  required?: boolean;
  idPrefix: string;
}) {
  const resolved = resolve(schema, root);
  const id = `${idPrefix}${path}`;
  const error = errors?.[path];
  const custom = override?.({ path, schema: resolved, value, onChange, error });
  const label = humanLabel(name, resolved);
  if (custom !== undefined) {
    return (
      <Field label={label} htmlFor={id} hint={resolved.description} error={error} required={required}>
        {custom}
      </Field>
    );
  }
  const type = primaryType(resolved);

  if (resolved.enum) {
    return (
      <Field label={label} htmlFor={id} hint={resolved.description} error={error} required={required}>
        <Select
          id={id}
          value={value == null ? undefined : String(value)}
          onValueChange={(v) => onChange(v)}
          options={resolved.enum.map((e) => ({ value: String(e), label: String(e) }))}
        />
      </Field>
    );
  }
  if (type === "boolean") {
    return (
      <div className="flex items-start justify-between gap-4 py-0.5">
        <div>
          <label htmlFor={id} className="text-xs font-medium">
            {label}
          </label>
          {resolved.description ? <p className="text-xs text-fg-subtle">{resolved.description}</p> : null}
        </div>
        <Switch id={id} checked={Boolean(value ?? resolved.default)} onCheckedChange={(c) => onChange(c)} />
      </div>
    );
  }
  if (type === "integer" || type === "number") {
    return (
      <Field label={label} htmlFor={id} hint={resolved.description} error={error} required={required}>
        <Input
          id={id}
          type="number"
          inputMode="decimal"
          aria-invalid={!!error}
          value={value == null ? "" : String(value)}
          min={resolved.minimum}
          max={resolved.maximum}
          placeholder={resolved.default != null ? String(resolved.default) : undefined}
          onChange={(e) => onChange(e.target.value === "" ? null : type === "integer" ? parseInt(e.target.value, 10) : Number(e.target.value))}
        />
      </Field>
    );
  }
  if (type === "string") {
    const long = /prompt|message|instructions|description|body|expression|template/i.test(name);
    return (
      <Field label={label} htmlFor={id} hint={resolved.description} error={error} required={required}>
        {long ? (
          <Textarea id={id} aria-invalid={!!error} value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} className="font-mono text-xs" rows={name.includes("prompt") ? 5 : 2} />
        ) : (
          <Input id={id} aria-invalid={!!error} value={(value as string) ?? ""} placeholder={resolved.default != null ? String(resolved.default) : undefined} onChange={(e) => onChange(e.target.value === "" && !required ? null : e.target.value)} />
        )}
      </Field>
    );
  }
  if (type === "array" && resolve(resolved.items ?? {}, root).type === "string") {
    const list = Array.isArray(value) ? (value as string[]) : [];
    return (
      <Field label={label} htmlFor={id} hint={resolved.description ?? "One per line"} error={error} required={required}>
        <Textarea id={id} rows={3} className="font-mono text-xs" value={list.join("\n")} onChange={(e) => onChange(e.target.value.split("\n").map((s) => s.trim()).filter(Boolean))} />
      </Field>
    );
  }
  if (type === "object" && resolved.properties) {
    const obj = (value ?? {}) as Record<string, unknown>;
    return (
      <fieldset className="flex flex-col gap-3 rounded-md border border-border p-3">
        <legend className="px-1 text-xs font-medium text-fg-muted">{label}</legend>
        {Object.entries(resolved.properties).map(([key, child]) => (
          <SchemaField
            key={key}
            path={`${path}.${key}`}
            name={key}
            schema={child}
            root={root}
            value={obj[key]}
            onChange={(v) => onChange({ ...obj, [key]: v })}
            errors={errors}
            override={override}
            required={resolved.required?.includes(key)}
            idPrefix={idPrefix}
          />
        ))}
      </fieldset>
    );
  }
  return (
    <Field label={label} htmlFor={id} hint={resolved.description ?? "JSON"} error={error} required={required}>
      <JsonField id={id} value={value ?? resolved.default ?? null} onChange={onChange} invalid={!!error} />
    </Field>
  );
}

/** Renders a form from a JSON Schema (as produced by Pydantic). Unknown shapes fall back to a JSON editor. */
export function JsonSchemaForm({ schema, value, onChange, errors, override, hidden = [], idPrefix = "f-" }: Props) {
  const root = resolve(schema, schema);
  return (
    <div className={cn("flex flex-col gap-3")}>
      {Object.entries(root.properties ?? {})
        .filter(([key]) => !hidden.includes(key))
        .map(([key, child]) => (
          <SchemaField
            key={key}
            path={key}
            name={key}
            schema={child}
            root={schema}
            value={value[key]}
            onChange={(v) => onChange({ ...value, [key]: v })}
            errors={errors}
            override={override}
            required={root.required?.includes(key)}
            idPrefix={idPrefix}
          />
        ))}
    </div>
  );
}
