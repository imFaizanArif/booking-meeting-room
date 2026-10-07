# Frontend conventions

The web app (`apps/web`) is a dense, serious operations console. These rules keep it
consistent and keep it from looking generated.

## Visual language

- **Colour means status.** Actions are monochrome (`bg-ink` primary, bordered secondary,
  ghost). Blue = running/info, amber = waiting/needs review, green = done, red = failed or
  destructive. Never use colour for decoration, never gradients, never glow.
- **Tokens only.** Use the Tailwind colour names mapped from CSS variables:
  `bg-bg`, `bg-surface`, `bg-subtle`, `bg-muted`, `border-border`, `border-border-strong`,
  `text-fg`, `text-fg-muted`, `text-fg-subtle`, `bg-ink`/`text-ink-fg`, and the status pairs
  `text-info`/`bg-info-bg`, `text-warn`/`bg-warn-bg`, `text-ok`/`bg-ok-bg`,
  `text-danger`/`bg-danger-bg`. No hex, no `gray-500`, no `blue-600`.
- **Type.** IBM Plex Sans (UI) and IBM Plex Mono (ids, JSON, code, idempotency keys).
  Body is `text-sm` (13px). Sizes: `text-2xs` 11, `text-xs` 12, `text-sm` 13, `text-base`
  14, `text-lg` 16, `text-xl` 20 (page titles only). Numbers in tables use `tabular`.
  Hierarchy comes from weight and colour (`font-medium`, `text-fg-muted`), not size jumps.
- **Density.** Controls are 28–32px tall (`h-7`/`h-8`). Table cells `px-3 py-2`. Page
  padding `px-8 py-6` via `PageContainer`. Use `gap-6`/`gap-8` between sections.
- **Shape.** Radius 4–6px (`rounded-sm`, `rounded-md`). Hairline borders. Shadows only on
  floating layers (menus, dialogs). No nested cards, no cards around every section: use
  `Section` (title + content) and `Panel` (one bordered surface) sparingly.
- **Motion.** Only overlays (dialog, drawer, popover, toast) animate, 120–200ms ease-out,
  via the `anim-*` classes. Buttons scale to 0.98 on press. Live status dots pulse. Nothing
  else moves. `prefers-reduced-motion` disables all of it.
- **Copy.** Sentence case. Buttons say what happens ("Approve and execute", "Save version",
  "Discover tools"), never "Submit"/"OK". Empty states say what the thing is and how to get
  one. Errors say what failed and what to do; show the request id from `ApiError`.
  No exclamation marks, no emoji, no "Oops".

## Building blocks (components/ui)

`Button`, `Input`, `Textarea`, `Field`/`FieldRow`, `Select`, `Switch`, `Checkbox`, `Modal`,
`Drawer`, `ConfirmDialog`, `Tabs*`, `Tooltip`, `DropdownMenu*`, `Popover*`, `Badge`, `Kbd`,
`StatusIndicator`, `RiskBadge`, `DataTable`, `CodeEditor`, `JsonViewer`, `JsonSchemaForm`,
`DiffViewer`, `EmptyState`, `LoadingState`, `Skeleton`, `ErrorState`, `PageHeader`,
`Section`, `DescriptionList`, `Metric`, `Panel`. Shell: `PageContainer`.

Every page has loading (`LoadingState`), empty (`EmptyState` or table `empty`), and error
(`ErrorState` with retry) states.

## Data access

- All HTTP goes through the generated client: `import { api, unwrap } from "@/lib/api/client"`.
  Paths and bodies are typed from `packages/api-client/src/schema.ts`
  (`pnpm gen:client` regenerates it from FastAPI). Types: `Schemas["ModelOut"]`.
- Per domain: `features/<domain>/queries.ts` (useQuery hooks) and `mutations.ts`
  (useMutation hooks that invalidate the right keys). Components never call `api` directly.
- Mutations show a toast on error automatically (MutationCache); pass
  `meta: { silent: true }` when the form shows the error inline instead.
- Forms: React Hook Form + Zod. Field errors from the server (`ApiError.fields`, each
  `{field, message}`) are mapped onto the form with `setError`.
- Role gating is cosmetic only (`canOperate(me.role)`); the backend enforces permissions.
