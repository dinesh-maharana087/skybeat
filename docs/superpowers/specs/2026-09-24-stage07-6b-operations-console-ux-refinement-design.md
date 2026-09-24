# Stage 07.6B Operations Console UX Refinement Design

## Status and goal

This design is approved for planning only. It refines the accepted Stage 07.6 dashboard into a three-view, server-rendered operations console that remains readable from a few devices to several hundred. It does not begin Stage 08 or change monitoring, identity, authorization, enrollment, credential, GPU-policy, history, or incident semantics.

The first authenticated operational page is **Overview** at `/dashboard`. **Devices** at `/dashboard/devices` is the fleet inventory and management workspace. **Projects** at `/dashboard/projects` is the project summary and creation workspace.

## Scope and invariants

- Continue using FastAPI, Jinja2, same-origin vanilla JavaScript, local CSS/SVG, and the existing dashboard authentication boundary.
- Keep the existing API/session/OIDC/CSP/no-store/same-origin mutation behavior. Do not place credentials, sessions, device telemetry, or sensitive state in browser storage.
- Do not introduce a frontend framework, chart library, WebSocket, SSE, polling transport change, database migration, offset pagination, or a download-and-merge fleet client workflow.
- Preserve the existing Stage 07.6 New Project, Add Device, one-time credential, project reassignment, monitoring enable/disable, detail drawer, incidents, history, abort-generation protections, and same-origin mutation behavior.
- Keep the existing 15-second visible and 60-second hidden cadence. Requests remain non-overlapping. A successful refresh updates page data in place; it does not reload the browser, reset navigation, clear filters, close the drawer, or scroll the workspace.
- Status wording and colors are presentation of canonical server values. The browser may format units, timestamps, and the online-count percentage only; it does not derive availability, GPU health, incident severity, or new health classes.

## Routes and shared shell

`GET /` remains the authenticated entry point. An unauthenticated request follows the existing Google-login redirect; an authenticated request redirects to `/dashboard`. `GET /dashboard`, `GET /dashboard/devices`, and `GET /dashboard/projects` each resolve the same dashboard user and render the same Jinja template with an `active_view` of `overview`, `devices`, or `projects`. Page responses remain `Cache-Control: no-store`.

The shared shell contains a compact deep-navy sidebar, workspace header, live/freshness status, identity, and logout action. Navigation links use the three explicit routes and expose the active item with both `aria-current="page"` and non-color treatment. A labelled keyboard-operable sidebar toggle persists only the string `collapsed` or `expanded` under one versioned local preference key. It stores no credentials, filters, tokens, telemetry, or project/device data. On narrow screens the sidebar is a labelled overlay/drawer; it is not permanently allocated horizontal width.

The visual system stays in `dashboard.css`: cool-slate workspace, restrained blue accent, emerald healthy, amber warning, coral/red critical, local SVG/CSS icons, stronger hierarchy, visible focus, and reduced-motion support. Status text remains visible in every status pill. No remote font, large icon library, or continuous animation is added.

## Read projection: Overview attention

The existing `GET /api/v1/dashboard/overview` response is extended, backward-compatibly, with `attention`. It is a single server-side bounded projection, never a browser merge of the fleet.

```json
{
  "attention": [
    {
      "device_id": "canonical UUID",
      "name": "display-safe device name",
      "project": {"project_id": "canonical UUID", "name": "display-safe project name"},
      "state": "OFFLINE",
      "gpu_health": {"effective": "DRIVER_ERROR"},
      "last_seen_at": "2026-09-24T10:00:00.000000Z",
      "has_active_incident": true
    }
  ]
}
```

Only existing canonical fields appear. The candidate predicate is the union of: canonical availability `OFFLINE`, `SUSPECT`, or `AWAITING_FIRST_HEARTBEAT`; GPU monitoring enabled with effective GPU state other than `OK`; or an existing active incident. A device that meets more than one condition occurs once. The projection contains at most 20 rows and has no cursor because it is a compact Overview summary.

The ordering is deterministic and a display ordering only, not a persisted severity policy: availability candidates sort by the existing canonical availability order `OFFLINE`, then `SUSPECT`, then `AWAITING_FIRST_HEARTBEAT`; devices included solely because of GPU/incident state follow. Within each group, active-incident presence sorts first, then oldest known `last_seen_at` (with no heartbeat first), then project name, device name, and device UUID. The API returns canonical state values instead of a synthetic reason, rank, or severity label. This prevents a new monitoring-health classification while making the fixed 20-row bound predictable.

The existing compact overview count and project projections remain unchanged. Overview obtains up to 10 recent incidents through the already-bounded incidents endpoint; it does not require a new incident API.

## View composition

### Overview

Overview contains the fleet title/live state, six differentiated canonical count cards, a textual fleet-health meter (`online / total` plus percentage when total is nonzero), the bounded attention list, a compact bounded project summary, and recent incidents. It never renders the complete inventory. Project cards use canonical counts and link to `/dashboard/devices?project_id=<canonical UUID>`. “View all projects” links to `/dashboard/projects`.

### Devices

Devices contains a compact productivity header, global debounced/existing-safe search, active-filter chips, a dense horizontally usable table, and Add Device. Device names continue to open the existing detail drawer. Project, Availability, and GPU Health filters move from the large standalone form into accessible header-popovers. They expose only existing API values and use single selection. Filter buttons describe their selection, support Enter/Space, Escape, focus restoration, and visible focus. Active chips offer individual removal and Clear all.

The table uses the existing opaque keyset cursor with a bounded page size of 25, 50, or 100, never above the API cap of 100. It shows previous/next controls and page context, not offset numbers or a fabricated total. A client-held cursor history starts at `null`; moving next records only the server-provided opaque next cursor and moving previous reuses the preceding known cursor. Any search, column-filter, page-size, project-link, or Clear-all change replaces that history with `[null]` and requests the first page.

Live refresh on a later keyset page requests the exact cursor currently represented by the history entry. It retains the active filters, page size, cursor history, current page position, open drawer, and workspace/table scroll position. The response replaces only that current page's bounded rows and next cursor. It never silently returns the operator to page one merely because the sorted fleet changed. If a current cursor is rejected or its page cannot be refreshed, the existing rows remain visible, the stale state is shown, and the operator may explicitly return to the first page; no cursor is guessed or regenerated client-side.

### Projects

Projects presents the existing project projection as a dedicated concise management page with canonical device counts and New Project. Selecting a project navigates to the Devices route with that project's canonical UUID filter. It adds no project deletion, membership, RBAC, organization administration, or new project semantics.

## Refresh and failure behavior

Each page controller requests only the bounded data it needs: Overview requests overview and recent incidents; Devices requests its current cursor page and projects required for its controls; Projects requests the existing project list. A `Promise.allSettled`-style page refresh retains successful portions when another bounded request fails. The global indicator reads “Live updates · updated …” after successful refresh and “Data stale · last updated …” after a failure; it never claims a socket connection. Existing abort/generation controls continue to protect detail and history refreshes, and a selected detail refresh is independent of whether its device remains on the visible table page.

## Accessibility, performance, and security

All dynamic values use `textContent`, safe DOM APIs, and safe URL construction. No `innerHTML`, raw JSON rendering, inline handler, unsafe HTML attribute construction, browser credential storage, or unbounded DOM rendering is allowed. The table header is sticky within the Devices workspace rather than making the entire application header sticky. Narrow layouts retain table horizontal access and make the existing drawer wider/full-screen as appropriate.

The implementation reuses existing DOM structure where practical, does not add listeners per refresh, clears superseded timers, and limits refresh work to the active page. Metric-change emphasis, if used, is brief, non-flashing, and disabled by `prefers-reduced-motion`.

## Testing and acceptance

Automated tests cover explicit page routes/authentication/active navigation; bounded deterministic attention projection; Overview's lack of full inventory; Devices inventory, filter controls/chips/keyset history/page cap/later-page refresh; Projects management; preserved drawer/mutations; non-overlapping visible/hidden polling; stale handling; safe DOM; no WebSocket/SSE/framework/chart library; and responsive/accessibility source guards.

No browser test framework is introduced. After code verification, status is recorded as `IMPLEMENTED / AWAITING BROWSER ACCEPTANCE`; Stage 07 remains open. Manual browser validation must cover desktop/narrow shell behavior, all three views, later-page refresh, filter keyboard operation, drawer/history persistence, all Stage 07.6 management actions, stale refresh behavior, and screenshots.
