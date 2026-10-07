/** Render a write-only secret hint ("…abcd") as "····abcd". */
export function maskHint(hint: string | null | undefined): string {
  if (!hint) return "····";
  return `····${hint.replace(/^…/, "")}`;
}
