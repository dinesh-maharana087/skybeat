# Stage 08A Design System Foundation Design

## Status and goal

This design is approved for specification review only. It establishes the reusable visual-system foundation for the existing SkyBeat dashboard without implementing it. Stage 08A makes the dashboard's visual language coherent for infrastructure, GPU, fleet, incident, and operational-management workflows while retaining the current product behavior and page composition.

Stage 07 remains `IMPLEMENTED / AWAITING BROWSER ACCEPTANCE`. Authorizing this Stage 08A specification does not accept Stage 07, remove its outstanding browser, real-device, or deployment checks, or authorize Stage 08B.

## Scope and invariants

- Keep FastAPI, Jinja2, same-origin vanilla JavaScript, local CSS/SVG, and the existing dashboard authentication/session boundary.
- Preserve all existing routes, endpoint contracts, Jinja sections and identifiers, data projections, device-health semantics, GPU-health semantics, incident semantics, filtering, keyset pagination, polling cadence, drawer behavior, dialog behavior, permissions, and server configuration.
- Preserve safe DOM construction. Dynamic values continue to use DOM APIs and `textContent`; `innerHTML`, unsafe attribute construction, raw JSON rendering, browser credential storage, and client-derived health logic remain prohibited.
- Do not add a frontend framework, a large UI framework, remote fonts, an icon-library dependency, a new chart library, WebSocket, SSE, a migration, an API change, or a backend change.
- Do not redesign the application shell/navigation, Overview, Devices, Projects, device-detail content, filters, table structure, incidents, information architecture, or responsive layout. Those remain later Stage 08 work.
- Do not alter JavaScript except, if implementation later requires it, to replace the four static history-series color literals with existing CSS design-token values while preserving the series, rendering, and data behavior exactly. Stage 08A does not otherwise refactor JavaScript.

## Current frontend boundary and token location

The dashboard consists of one server-rendered template (`server/app/templates/dashboard.html`), one stylesheet (`server/app/static/dashboard.css`), and one DOM-safe controller (`server/app/static/dashboard.js`). `dashboard.css` is therefore the canonical Stage 08A design-system location. No new runtime stylesheet, component library, build system, or design-token service is introduced.

The implementation will keep existing template classes and IDs stable. It may add additive semantic classes or data attributes only where a common primitive cannot be applied safely through existing selectors. It will not use those additions to change DOM hierarchy, route/view composition, or event wiring.

## Token architecture

The system uses three strictly ordered layers. A lower layer must not refer to a higher layer.

```text
primitive tokens  ->  semantic tokens  ->  component tokens/rules
raw visual values     purpose-specific     element-level consumption
```

### Primitive tokens

Primitive tokens are the only tokens permitted to contain raw color, dimension, font, radius, or shadow values. They establish a compact, restrained scale and are intentionally not named after specific dashboard components.

```css
:root {
  /* Cool neutral palette */
  --sb-color-slate-25: ...;
  --sb-color-slate-50: ...;
  --sb-color-slate-100: ...;
  --sb-color-slate-200: ...;
  --sb-color-slate-300: ...;
  --sb-color-slate-500: ...;
  --sb-color-slate-700: ...;
  --sb-color-slate-900: ...;
  --sb-color-navy-800: ...;
  --sb-color-navy-900: ...;
  --sb-color-blue-50: ...;
  --sb-color-blue-100: ...;
  --sb-color-blue-600: ...;
  --sb-color-blue-700: ...;
  --sb-color-green-50: ...;
  --sb-color-green-700: ...;
  --sb-color-amber-50: ...;
  --sb-color-amber-700: ...;
  --sb-color-red-50: ...;
  --sb-color-red-700: ...;

  /* Spacing and geometry */
  --sb-space-1: 0.25rem;
  --sb-space-2: 0.5rem;
  --sb-space-3: 0.75rem;
  --sb-space-4: 1rem;
  --sb-space-5: 1.25rem;
  --sb-space-6: 1.5rem;
  --sb-space-8: 2rem;
  --sb-radius-sm: ...;
  --sb-radius-md: ...;
  --sb-radius-lg: ...;
  --sb-shadow-sm: ...;
  --sb-shadow-md: ...;

  /* Typography and interaction */
  --sb-font-sans: ...;
  --sb-font-mono: ...;
  --sb-font-size-xs: ...;
  --sb-font-size-sm: ...;
  --sb-font-size-md: ...;
  --sb-font-size-lg: ...;
  --sb-font-size-xl: ...;
  --sb-line-height-tight: ...;
  --sb-line-height-normal: ...;
  --sb-focus-ring-width: 0.1875rem;
  --sb-control-height: ...;
}
```

The exact palette values are selected during implementation to meet contrast requirements. They will be light cool gray for the workspace, white/near-white surfaces, deep navy/blue-black for the sidebar, controlled blue for the primary action, and muted non-neon operational hues. Primitive colors are not used directly by component selectors except where a semantic token would not add meaning (for example, a palette key used to build another token).

### Semantic tokens

Semantic tokens express purpose and are the normal interface consumed by component rules. The public, stable semantic names are:

```css
:root {
  /* Backgrounds and foregrounds */
  --sb-bg-app: var(--sb-color-slate-50);
  --sb-bg-surface: ...;
  --sb-bg-surface-secondary: ...;
  --sb-bg-sidebar: ...;
  --sb-bg-hover: ...;
  --sb-bg-selected: ...;
  --sb-text-primary: ...;
  --sb-text-secondary: ...;
  --sb-text-muted: ...;
  --sb-text-inverse: ...;
  --sb-border: ...;
  --sb-border-strong: ...;
  --sb-focus-ring: ...;

  /* Brand/action */
  --sb-primary: ...;
  --sb-primary-hover: ...;
  --sb-primary-soft: ...;

  /* Operational status */
  --sb-success: ...;
  --sb-success-soft: ...;
  --sb-warning: ...;
  --sb-warning-soft: ...;
  --sb-danger: ...;
  --sb-danger-soft: ...;
  --sb-info: ...;
  --sb-info-soft: ...;
  --sb-neutral: ...;
  --sb-neutral-soft: ...;
}
```

The foreground and soft-background pair for each operational state must maintain readable text contrast. Soft status backgrounds cannot be the sole signal; the canonical text label remains visible. `--sb-danger` is reserved for critical/error/offline meaning and destructive actions, not decorative emphasis. Green is reserved for healthy/success, amber for warning/degraded, blue for informational/active selection, and gray for neutral/unknown/unavailable.

### Component tokens and rules

Component tokens adapt semantic purpose to a reusable visual primitive. They may alias semantic tokens but may not define unrelated literal colors or arbitrary geometry. Examples include:

```css
:root {
  --sb-control-bg: var(--sb-bg-surface);
  --sb-control-border: var(--sb-border-strong);
  --sb-control-focus-ring: var(--sb-focus-ring);
  --sb-button-primary-bg: var(--sb-primary);
  --sb-table-header-bg: var(--sb-bg-surface-secondary);
  --sb-status-ok-fg: var(--sb-success);
  --sb-status-ok-bg: var(--sb-success-soft);
  --sb-drawer-bg: var(--sb-bg-surface);
}
```

Component tokens and primitive classes are defined before page-specific selectors. Existing component selectors consume them rather than recreating colors, borders, radii, padding, or shadows. This permits later Stage 08 page work to compose the same foundation without proliferating one-off CSS.

## Typography and technical values

The base font remains a local system sans-serif stack; no network font is introduced. A local system monospace stack is available for machine-oriented values.

| Role | Intended use | Style rule |
| --- | --- | --- |
| Page title | Existing page heading | restrained `xl` scale, compact line height, semibold; never marketing-sized |
| Section title | Existing section headings | `lg` scale, semibold |
| Card title | metric/project/detail card labels | `sm` or `md`, semibold |
| Body | descriptions and values | `md`, normal line height |
| Secondary/metadata | timestamps, helper text, summaries | `sm` or `xs`, `--sb-text-secondary` or `--sb-text-muted` |
| Table header | operational column labels | `xs`, uppercase only where already appropriate, tracked but readable |
| Metric value | existing count/measurement presentation | tabular numerals, `lg` scale, semibold |
| Metric label | existing metric caption | `xs`/`sm`, secondary text |
| Technical value | UUIDs, IPs, versions, device/GPU identifiers | `--sb-font-mono`, tabular numerals, wrapping/breaking preserved |

Technical styling communicates scanability, not sensitivity. It must not expose additional data, remove escaping, or turn values into executable/clickable content. Long values retain `overflow-wrap: anywhere` and are never clipped in a way that prevents inspection.

## Spacing, surfaces, and layout foundations

All component spacing uses `--sb-space-*` tokens. The intended rhythm is: one token for tight inline gaps, two/three for related control or list gaps, four/five for card/form padding, six/eight for section and workspace separation. Existing responsive `clamp`, grid, horizontal table overflow, and media-query behavior remains structurally unchanged.

Reusable visual primitives are:

- **Surface / section container:** `--sb-bg-surface`, one subtle border, medium radius, and no or small shadow.
- **Standard card:** a surface with tokenized padding and no decorative status color; use only when it represents a real information group.
- **Metric card:** a standard card with the existing metric typography and a restrained semantic accent rule where it communicates a real category.
- **Interactive card:** a standard card with tokenized hover and focus-within treatment; it must remain usable without hover.
- **Attention surface:** a standard surface with a semantic border/background accent for a real warning/critical condition; it preserves text labels and does not become a giant color block.

Nested cards are not added merely for visual decoration. Existing nested content is migrated only when its hierarchy is already meaningful. Shadows remain minimal; borders, spacing, and typographic contrast do most of the grouping work.

## Controls and buttons

Inputs, selects, search fields, filter controls, checkboxes, and labels share a tokenized baseline: one control height, consistent horizontal padding, surface background, border, radius, readable placeholder, disabled appearance, and visible focus ring. Form labels retain a readable small/secondary hierarchy and programmatic associations.

The reusable button model has five variants:

- **Primary:** blue fill for the main non-destructive action in a local action group.
- **Secondary:** surface/background with a defined border for ordinary actions.
- **Ghost:** quiet transparent/surface-minimal action, never the only discoverable presentation for destructive operations.
- **Danger:** destructive/critical action only; it does not represent generic errors or status display.
- **Icon:** a square/compact labelled control with an accessible name; icons support rather than replace essential operational text.

All variants share a standard height, padding scale, radius, semibold text, hover, active, disabled, and focus behavior. Existing buttons are mapped to variants by role; button behavior, IDs, listeners, and text remain unchanged in Stage 08A.

## Table foundation

The existing device table structure, columns, filters, pagination, keyset semantics, sticky behavior, and horizontal-overflow behavior remain unchanged. The shared table foundation standardizes:

- secondary-surface table header, readable header typography, and clear header-to-row separation;
- compact, tokenized row/cell padding suited to dense monitoring data;
- subtle row dividers, hover/focus-within affordances, and existing selected/filter state presentation;
- tabular numeric alignment where the existing data layout permits it;
- status cells that contain the common status indicator rather than bespoke color treatment.

No table is restructured, reordered, made sortable, virtualized, or assigned new data behavior during Stage 08A.

## Operational status system

Status presentation is a reusable compact indicator composed of a small dot, a soft semantic background, and the canonical text label. The dot is supplementary. Text is mandatory, so status does not rely on color alone. Where possible, a CSS class reflects a canonical status value rather than a newly inferred browser category.

| Canonical state(s) | Semantic presentation | Required visible text |
| --- | --- | --- |
| `ONLINE`, `OK`, `HEALTHY`, `RESOLVED` | success | canonical label |
| `SUSPECT`, `WARNING`, `DEGRADED` | warning | canonical label |
| `OFFLINE`, `CRITICAL`, `DRIVER_ERROR`, `GPU_MISSING`, `NVIDIA_SMI_FAILED` | danger | canonical label |
| `AWAITING_FIRST_HEARTBEAT`, `ACTIVE` | info | canonical label |
| `UNKNOWN`, `NOT_MONITORED`, unavailable/null display states | neutral | canonical display label |

`ACTIVE` remains an incident-lifecycle label, not an availability or GPU-health inference. `AWAITING_FIRST_HEARTBEAT` remains its distinct server-owned availability state. The UI must not translate, collapse, rank, or derive status meaning beyond presentation of existing canonical values.

## Drawer, dialog, and panel foundations

The existing device-detail drawer and native dialogs retain their markup, opening/closing behavior, focus behavior, ARIA relationships, and content. Stage 08A supplies shared styling rules only:

- drawer/panel surface, border, restrained shadow, padding, header/title/subtitle, section spacing, divider, close action, and optional footer;
- dialog surface, backdrop, header, content/form spacing, action area, warning/credential attention surface, and close action;
- consistent use of typography, control, status, and technical-value primitives within these existing structures.

There is no drawer-content redesign, modal-flow redesign, focus-trap replacement, new modal, or new panel during this stage.

## Iconography

The current UI is primarily text-led and has no installed icon library. Stage 08A keeps that low-dependency approach. Existing textual marks or symbols are not supplemented with mixed emoji or unrelated icon sets. If a small CSS/local-SVG icon is necessary for a pre-existing labelled control, it follows the same simple local icon language and always retains an accessible name. No icon-only control may conceal a required operational label.

## Accessibility and responsive foundation

Every keyboard-operable control, link, filter control, table action, drawer action, and dialog action receives a consistent high-contrast `:focus-visible` ring using `--sb-focus-ring` and `--sb-focus-ring-width`. Hover styles are additive, not required for comprehension. Disabled controls retain sufficient distinction without being mistaken for static text. Muted text is selected for readable contrast on its intended surface.

Status text remains visible with its dot and tint. Textual refresh/stale/error messages remain unchanged. The existing reduced-motion rule continues to disable nonessential transitions. Tokens use relative units and existing responsive layouts keep their fluid/grid/overflow approach; Stage 08A adds no fixed dashboard-width assumption.

## Migration boundaries

Implementation is incremental and CSS-first:

1. Introduce the layered token block and tokenized base/primitive rules in `dashboard.css`.
2. Migrate existing shared selectors—shell colors, typography, common controls, buttons, surfaces, status pills, table, drawer, dialogs, and history visual colors—to those primitives without changing their structures.
3. Add narrowly scoped static/source tests for token presence, status-label semantics, focus/reduced-motion support, and preservation of existing dashboard safety/behavior guards.
4. Document the implementation and verification in `docs/IMPLEMENTATION_STATUS.md` only after verified work exists.

Stage 08A explicitly excludes shell/navigation redesign (08B); Overview, Devices, Projects, detail, incident, and filter-layout redesign; new widgets; responsive re-layout; new iconography framework; JavaScript cleanup; and backend work. Existing page-specific selectors may remain temporarily when their migration would alter layout or risk interaction behavior; they are recorded as debt for later scoped work, not opportunistically rewritten.

## Testing and verification strategy

Automated regression coverage must retain the existing tests for dashboard authentication, routes, active view rendering, identifiers, canonical data display, polling cadence/non-overlap, filters, opaque keyset pagination, drawer/history behavior, management dialogs, and DOM safety. New focused source-level tests verify:

- the three-layer `--sb-*` architecture and required semantic token families;
- absence of new arbitrary status colors in common component rules;
- status presentation has visible canonical text in addition to a dot/tint;
- common focus-visible and reduced-motion behavior remains present;
- controls, tables, drawer/dialog, and technical-value foundations use shared primitives;
- no new frontend dependency, unsafe DOM API, local sensitive storage, WebSocket, SSE, endpoint, or polling change appears.

After implementation, run the affected dashboard tests, full server suite as appropriate, Ruff and formatting checks, strict mypy if affected Python code exists, and a build/application smoke check if configured. Browser acceptance, when a suitable local environment is available, verifies authenticated load, navigation, data rendering, filters, pagination, drawer/dialog flows, polling, keyboard focus, reduced motion, responsive behavior, and no new console errors. Browser checks remain evidence for Stage 08A only; they do not retroactively close Stage 07 unless its separately recorded acceptance criteria are completed.

## Acceptance criteria

Stage 08A is complete only when all of the following are true:

1. `dashboard.css` contains centralized, layered `--sb-*` primitive, semantic, and component tokens for backgrounds, text, borders, brand/action, operational states, geometry, shadows, spacing, typography, and focus.
2. Shared component foundations exist for surfaces/cards, controls, button variants, operational status indicators, tables, drawer/panel elements, dialogs, and technical values.
3. Common existing dashboard elements consume the foundation without a broad Jinja or JavaScript rewrite.
4. Operational status uses canonical visible text plus a compact dot/tint; color never supplies status meaning alone.
5. Existing behavior—including API/authentication, routes, polling, filtering, keyset pagination, drawer/dialog behavior, and canonical server-owned health semantics—is unchanged.
6. No migration, backend/API/server/deployment/Caddy change, frontend framework, large UI library, remote font, or external icon system is introduced.
7. Focus visibility, contrast, disabled/hover behavior, reduced motion, and current responsive foundations remain usable.
8. Targeted tests and configured quality checks pass, visual/regression risks are recorded, and the implementation status is updated factually.
9. Stage 08B and all page-level redesign work remain unstarted.

## Risks and deferred technical debt

The single large stylesheet currently mixes global, component, and page-specific rules. Stage 08A reduces new duplication but deliberately does not split the stylesheet or refactor JavaScript, because either change would exceed the safe foundation scope. Some current literal values may remain in page-specific/chart selectors until a later scope can migrate them without layout changes. The exact palette must be checked in a browser for contrast and operational distinguishability; static CSS tests cannot prove rendered contrast or browser interaction behavior.

No implementation plan accompanies this document yet. Per the agreed process, the next step is review and approval of this specification; implementation planning begins only after that approval.
