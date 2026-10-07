"use client";

import { autocompletion, type CompletionContext, type CompletionResult } from "@codemirror/autocomplete";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import type { Extension } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import CodeMirror from "@uiw/react-codemirror";
import * as React from "react";

import { cn } from "@/lib/utils";

const tokens = EditorView.theme({
  "&": { color: "var(--fg)", backgroundColor: "var(--surface)" },
  ".cm-content": { caretColor: "var(--fg)", fontFamily: "var(--font-mono)", padding: "6px 0" },
  ".cm-cursor": { borderLeftColor: "var(--fg)" },
  ".cm-activeLine": { backgroundColor: "color-mix(in oklch, var(--subtle) 70%, transparent)" },
  ".cm-activeLineGutter": { backgroundColor: "transparent", color: "var(--fg-muted)" },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground": { backgroundColor: "oklch(0.58 0.14 255 / 0.2) !important" },
  ".cm-tooltip": { border: "1px solid var(--border)", backgroundColor: "var(--surface)", borderRadius: "6px" },
  ".cm-tooltip-autocomplete > ul > li[aria-selected]": { backgroundColor: "var(--subtle)", color: "var(--fg)" },
});

function variableCompletions(names: string[]) {
  return (context: CompletionContext): CompletionResult | null => {
    const word = context.matchBefore(/\{\{\s*[\w.]*/);
    if (!word || (word.from === word.to && !context.explicit)) return null;
    const start = word.text.replace(/\{\{\s*/, "");
    return {
      from: word.to - start.length,
      options: names.map((name) => ({ label: name, type: "variable" })),
      validFor: /^[\w.]*$/,
    };
  };
}

interface CodeEditorProps {
  value: string;
  onChange?: (value: string) => void;
  language?: "json" | "template" | "text";
  readOnly?: boolean;
  minHeight?: string;
  maxHeight?: string;
  completions?: string[];
  className?: string;
  ariaLabel?: string;
  invalid?: boolean;
}

export function CodeEditor({ value, onChange, language = "json", readOnly, minHeight = "120px", maxHeight = "480px", completions, className, ariaLabel, invalid }: CodeEditorProps) {
  const extensions = React.useMemo<Extension[]>(() => {
    const ext: Extension[] = [tokens, EditorView.lineWrapping, EditorView.contentAttributes.of({ "aria-label": ariaLabel ?? "Code editor" })];
    if (language === "json") ext.push(json());
    if (language === "template") ext.push(markdown());
    if (completions?.length) ext.push(autocompletion({ override: [variableCompletions(completions)] }));
    return ext;
  }, [language, completions, ariaLabel]);

  return (
    <div
      className={cn(
        "overflow-hidden rounded-md border border-border-strong focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/25",
        invalid && "border-danger",
        className,
      )}
    >
      <CodeMirror
        value={value}
        onChange={onChange}
        readOnly={readOnly}
        editable={!readOnly}
        extensions={extensions}
        theme="none"
        minHeight={minHeight}
        maxHeight={maxHeight}
        basicSetup={{ foldGutter: language === "json", highlightActiveLine: !readOnly, autocompletion: !completions }}
      />
    </div>
  );
}
