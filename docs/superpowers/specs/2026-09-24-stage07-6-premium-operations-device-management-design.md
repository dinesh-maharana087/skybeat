# Stage 07.6 Premium Operations UI and Device Management Design

## Goal

Polish the accepted Stage 07 dashboard into a compact, professional operations console and add safe browser workflows for project creation, device enrollment, project reassignment, and device enablement changes. Preserve all accepted monitoring, authentication, history, and agent behavior.

## Scope and boundaries

- Stage 07.1 through 07.5 remain accepted and compatible.
- The dashboard remains a single FastAPI/Jinja2 page using same-origin vanilla JavaScript and CSS. No SPA, UI framework, remote font, external icon library, chart library, or migration is introduced.
- The browser never derives availability, GPU health, incidents, history, or credential material. Existing server projections remain authoritative.
- Stage 08 capabilities, remote administration, delete operations, project editing, project deletion, archiving, membership, RBAC, organization administration, agent protocol changes, and monitoring lifecycle changes are out of scope.
- This stage does not change the Stage 07.2 history endpoint, server bounds/downsampling, polling cadence, OIDC implementation, opaque session implementation, CSP, no-store responses, or device identity semantics.

## Operations UI

The existing page becomes an application shell without creating fake routes. A compact sidebar contains SkyBeat identity, anchor navigation to Overview, Devices, and Projects, and a quiet version/footer area. The main workspace has a compact header with the current identity, logout action, live/freshness indicator, a human-readable last-successful refresh, and exact time in accessible title text.

CSS custom properties define a restrained token system for navy/slate navigation, neutral workspace surfaces, borders, text, muted text, blue/cyan accent, success, warning, danger, radius, shadow, spacing, and transition timing. Status remains textual as well as colored. The layout supports desktop first, then 1024px, 768px, and narrow screens; it respects `prefers-reduced-motion`.

Fleet cards, the awaiting-first-heartbeat indicator, project health, filters, device inventory, detail drawer, GPU data, and accepted native-SVG history are visually reorganized only. Table status/GPU labels use canonical server values. JavaScript may format percentages, byte values, and timestamps for display but must preserve null values and use no presentation value to infer monitoring state.

## Canonical mutation boundary

The backend reuses `IdentityService` rather than adding separate dashboard business logic. Each mutation constructs that service with the existing authenticated dashboard user email as its audit actor.

All new mutation routes are authenticated through the existing dashboard identity boundary, require the existing same-origin mutation protection, validate JSON input at the server boundary, return safe errors with `Cache-Control: no-store`, and never log credential bodies. They expose projections rather than ORM objects.

Approved route contracts are:

- `POST /api/v1/projects`: accepts required canonical project `name`; calls `IdentityService.create_project()` and returns a display-safe project projection.
- `POST /api/v1/devices`: accepts device `name`, canonical project UUID, and the already-supported GPU monitoring/count policy; calls `IdentityService.enroll()`. It returns a display-safe new-device projection plus the generated device credential exactly in the successful enrollment response. The server generates both UUID and credential; it stores only the credential digest.
- `PATCH /api/v1/devices/{device_uuid}/project`: accepts a canonical project UUID; calls `IdentityService.move()`.
- `PATCH /api/v1/devices/{device_uuid}/monitoring`: accepts an explicit boolean; calls `IdentityService.set_enabled()`.

No route accepts a credential in a URL, query parameter, header echo, data attribute, browser storage, or audit/log payload. The enrollment response is no-store and not replayed from storage. Its plaintext credential is rendered once in the open modal through text-only DOM APIs, copied only on an explicit user action, and cleared from JavaScript/DOM state when dismissed.

## User workflows

`+ New Project` opens a small accessible dialog with only the canonical required project name. It prevents duplicate submission, reports validation/server errors safely, and refreshes canonical projects and overview after success. When launched from enrollment, the new project is selected for that in-progress form.

`+ Add Device` opens an accessible dialog. The user selects an existing or newly created project, supplies the device name, and chooses only the existing GPU monitoring/count policy fields. Success displays the server-generated enrollment credential once, with a clear one-time warning and Copy action. It then refreshes the overview, project summary, and inventory and may open the newly created canonical detail.

The detail drawer exposes Change Project and Enable/Disable only through explicit confirmation. Each action calls its canonical route, prevents duplicate submits, and refreshes affected canonical views after server confirmation. No local mutation is treated as success before the response arrives.

## Security and failure handling

Dashboard sessions, Google OIDC, same-origin requests, CSP, and text-only DOM insertion remain intact. The development dashboard-auth bypass, if explicitly configured, uses the same dashboard identity boundary; it does not create a separate unprotected mutation path.

Invalid project UUIDs, inactive projects, unknown devices, invalid policies, conflicts, unauthenticated requests, and failed same-origin checks return safe status-specific errors. The browser retains form values after safe errors, shows retry only for idempotent/reviewed operations, and leaves the server authoritative.

## Testing and acceptance

Automated coverage includes visual shell/static safety boundaries, preservation of existing filters/detail/history/polling, authenticated and same-origin mutation enforcement, rejected invalid/unknown/inactive project input, duplicate-submission guards, canonical service use, no credential logging/storage/URL data, one-response credential behavior, project selection after creation, reassignment, enable/disable, and existing dashboard/OIDC regressions.

Run the affected dashboard/configuration tests, full server suite, Ruff check/format, strict mypy, Alembic heads/history, deployment validator, and `git diff --check`. No agent suite is required unless an agent/shared-contract/deployment artifact changes. Real-MySQL mutation tests remain environment-pending if the retained instance cannot be safely started; no ACL, data, reset, or initialization change is allowed to make them run.

After executable checks, Stage 07.6 is recorded as IMPLEMENTED / AWAITING VISUAL ACCEPTANCE. Manual browser acceptance verifies overview, filters, table, drawer, GPU data, history, device enrollment, project creation/reassignment, enable/disable, and responsive layouts. Stage 07 and Stage 08 remain incomplete until separately accepted.
