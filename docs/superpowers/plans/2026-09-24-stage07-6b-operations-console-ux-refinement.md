# Stage 07.6B Operations Console UX Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine the authenticated Stage 07.6 dashboard into bounded Overview, Devices, and Projects operations views without changing monitoring or management semantics.

**Architecture:** Keep the FastAPI/Jinja2/vanilla-JavaScript modular monolith. Add one backward-compatible, capped server read projection for Overview attention; page routes share the existing authentication/template shell. The browser renders only the active view, preserves opaque-keyset state locally in memory, and continues visibility-aware non-overlapping polling.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Jinja2, local CSS/SVG, vanilla DOM APIs, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-24-stage07-6b-operations-console-ux-refinement-design.md`

## Global Constraints

- Implement Stage 07.6B only; do not begin Stage 08 or modify heartbeat, availability, GPU confirmation, incident, identity, credential, OIDC, session, CSP, CSRF, or history semantics.
- Do not add a migration, database schema, framework, remote font, remote icon package, chart library, WebSocket, SSE, message broker, or offset pagination.
- `attention` is one server-side projection capped at exactly 20 possible rows; do not download or merge a fleet in browser JavaScript.
- Attention candidates and displayed fields use existing canonical availability, GPU, and incident state only. Do not persist or return an invented severity/reason/rank.
- Preserve `GET /api/v1/dashboard/overview`, `/api/v1/devices`, `/api/v1/projects`, current keyset cursor format/cap, same-origin mutation routes, one-time enrollment credential behavior, detail/history race protection, and no-store headers.
- Dynamic values use DOM creation, `textContent`, safe attributes, and `encodeURIComponent`/`URLSearchParams`. Do not use `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, inline handlers, `eval`, raw payload rendering, or browser credential storage.
- Refresh remains 15 seconds while visible and 60 seconds while hidden. It is non-overlapping, preserves current state, and never reloads the document.
- Do not commit, push, touch retained MySQL data/ACLs, reset or initialize MySQL, run production operations, or change existing unrelated worktree changes.

## Review Focus

- A device matching both OFFLINE and GPU-error predicates appears exactly once in attention; Task 1 owns the projection test.
- The twenty-first deterministically ordered candidate is absent while all returned rows retain canonical fields; Task 1 owns the cap/order test.
- Refreshing a later keyset page sends its known opaque cursor, retains the page history/drawer/scroll state, and never falls back to page one; Task 3 owns the static/controller test.
- A keyboard user can open, choose, close, and regain focus from each column filter without relying on hover; Task 3 owns the template/controller accessibility test.
- A failed page-specific refresh retains rendered data and declares it stale without starting parallel timers or requests; Task 4 owns the polling/failure test.

---

## File structure

| File | Responsibility |
| --- | --- |
| `server/app/dashboard/read.py` | Existing bounded projections; gains the deterministic capped attention projection. |
| `server/app/api/dashboard.py` | Keeps the overview route contract and returns the extended projection unchanged otherwise. |
| `server/app/api/dashboard_page.py` | Authenticated root redirect and the three route handlers that render a shared template context. |
| `server/app/templates/dashboard.html` | Shared application shell and conditional, semantic markup for Overview, Devices, and Projects. |
| `server/app/static/dashboard.js` | View-aware DOM rendering, navigation preference, filters, keyset history, and page-specific polling while retaining drawer/history/management logic. |
| `server/app/static/dashboard.css` | Design tokens, responsive shell, dense table, popovers, active chips, and reduced-motion/focus styling. |
| `server/tests/test_dashboard_read.py` | Pure projection/canonical-field tests. |
| `server/tests/test_dashboard_stage07_read.py` | Database-backed dashboard read-contract coverage where current fixtures support it. |
| `server/tests/test_dashboard_api.py` | Authenticated overview extension/no-store API checks. |
| `server/tests/test_dashboard_page.py` | Route, template, static DOM, safe-source, pagination, polling, and accessibility guards. |
| `docs/API_SPEC.md` | Backward-compatible Overview `attention` field documentation. |
| `docs/IMPLEMENTATION_STATUS.md` | Updated only after implementation and verification, never during planning. |

### Task 1: Add the capped canonical Overview attention read projection

**Files:**

- Modify: `server/app/dashboard/read.py`
- Modify: `server/tests/test_dashboard_read.py`
- Modify: `server/tests/test_dashboard_stage07_read.py`
- Modify: `server/tests/test_dashboard_api.py`
- Modify: `docs/API_SPEC.md`

**Interfaces:**

- Produces `ATTENTION_LIMIT = 20` in `app.dashboard.read`.
- Produces `_attention_view(device: Device, project: Project, has_active_incident: bool) -> dict[str, object]` with `device_id`, `name`, `project`, `state`, `gpu_health.effective`, `last_seen_at`, and `has_active_incident` only.
- Extends `DashboardReadService.overview() -> dict[str, object]` with `"attention": list[dict[str, object]]`; all existing keys retain their meanings.
- `GET /api/v1/dashboard/overview` continues to return this projection behind `DashboardUserDependency` and `Cache-Control: no-store`.

- [ ] **Step 1: Write failing projection tests for canonical candidates, deduplication, order, and cap**

  Add tests that construct devices/project records using the existing dashboard read test style. Assert that the returned Overview projection contains a maximum of 20 items, one row for a device that is both OFFLINE and `DRIVER_ERROR`, only the approved keys, and this canonical display sequence: OFFLINE, SUSPECT, AWAITING_FIRST_HEARTBEAT, GPU/incident-only. For equal categories, assert active incident first, then no heartbeat/oldest `last_seen_at`, project name, device name, and UUID.

  ```python
  def test_attention_projection_is_deduplicated_capped_and_canonical() -> None:
      payload = service.overview()

      attention = payload["attention"]
      assert len(attention) == 20
      assert [item["device_id"] for item in attention].count(offline_gpu.device_uuid) == 1
      assert [item["state"] for item in attention[:3]] == [
          "OFFLINE", "SUSPECT", "AWAITING_FIRST_HEARTBEAT",
      ]
      assert set(attention[0]) == {
          "device_id", "name", "project", "state", "gpu_health", "last_seen_at",
          "has_active_incident",
      }
      assert "severity" not in attention[0]
      assert "reason" not in attention[0]
  ```

- [ ] **Step 2: Run the new projection tests and verify RED**

  Run from `server`:

  ```text
  ..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_read.py tests/test_dashboard_stage07_read.py -q
  ```

  Expected: FAIL because `overview()` has no `attention` field or bounded candidate query.

- [ ] **Step 3: Implement one bounded server-side candidate query**

  In `read.py`, add the constant and projection helper:

  ```python
  ATTENTION_LIMIT = 20


  def _attention_view(
      device: Device, project: Project, has_active_incident: bool
  ) -> dict[str, object]:
      return {
          "device_id": device.device_uuid,
          "name": device.name,
          "project": {"project_id": project.public_id, "name": project.name},
          "state": _state(device),
          "gpu_health": {"effective": effective_gpu_state(device)},
          "last_seen_at": _timestamp(device.last_seen_at),
          "has_active_incident": has_active_incident,
      }
  ```

  Inside `DashboardReadService.overview`, build a correlated active-incident `exists` expression. Filter with the union of `state_expression.in_(("OFFLINE", "SUSPECT", "AWAITING_FIRST_HEARTBEAT"))`, GPU monitoring enabled/effective state not `OK`, and that `exists` expression. Select `Device`, `Project`, and the boolean incident expression; do not join incidents directly, because that would duplicate devices.

  Order using SQL `case` expressions for the specified canonical availability order, active-incident boolean, null/old `last_seen_at`, `Project.name`, `Device.name`, and `Device.device_uuid`; apply `.limit(ATTENTION_LIMIT)`. Convert only the resulting rows with `_attention_view` and add the list to the existing response. The ordering expressions are local query presentation mechanics and are not returned as fields.

- [ ] **Step 4: Document the backward-compatible API field**

  In `docs/API_SPEC.md`, add `attention` to the overview response with the exact field shape, fixed maximum of 20, canonical candidate predicate, deduplication rule, deterministic ordering, and statement that it is not a severity classification or cursor endpoint.

- [ ] **Step 5: Add authenticated route regression coverage**

  Extend the existing authorized Overview fake/read-service test to return an `attention` list and assert the route returns it unchanged with `Cache-Control: no-store`. Preserve the existing assertion that unauthorized requests fail before database access.

  ```python
  def test_authorized_overview_returns_bounded_attention_projection() -> None:
      overview = client.get("/api/v1/dashboard/overview")

      assert overview.status_code == 200
      assert overview.headers["cache-control"] == "no-store"
      assert overview.json()["attention"][0]["state"] == "OFFLINE"
  ```

- [ ] **Step 6: Run focused tests and static checks**

  ```text
  ..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_read.py tests/test_dashboard_stage07_read.py tests/test_dashboard_api.py -q
  ..\.venv\Scripts\ruff.exe check --no-cache app tests
  ..\.venv\Scripts\mypy.exe app --strict --cache-dir D:\skybeat\.stage07-6b-task1-mypy-cache
  ```

  Expected: tests pass; Ruff and strict mypy report no new findings.

### Task 2: Create authenticated three-view routes and conditional shared markup

**Files:**

- Modify: `server/app/api/dashboard_page.py`
- Modify: `server/app/templates/dashboard.html`
- Modify: `server/tests/test_dashboard_page.py`

**Interfaces:**

- Produces `render_dashboard_view(request: Request, active_view: Literal["overview", "devices", "projects"]) -> Response` after resolving the existing `DashboardUser`.
- `GET /` resolves auth then responds `303` to `/dashboard`; no-session behavior remains a `303` to `/auth/google/login`.
- `GET /dashboard`, `/dashboard/devices`, and `/dashboard/projects` render the same template with `user_email` and `active_view`, status 200, and `Cache-Control: no-store`.
- Template exposes `data-dashboard-view="{{ active_view }}"`, route-based navigation, `aria-current="page"`, sidebar toggle, and only active-view content. Shared dialogs may be retained where their current workflows need them.

- [ ] **Step 1: Write failing page-route and markup tests**

  Add tests for unauthenticated root redirect, authenticated root redirect to `/dashboard`, and each route rendering its assigned page only. Assert the Overview response lacks the device table, the Devices response contains it, and the Projects response contains New Project/project summaries. Assert route links—not hash links—active navigation, a labelled sidebar toggle, and an escaped hostile authenticated email.

  ```python
  def test_authenticated_dashboard_routes_render_one_active_view() -> None:
      assert client.get("/", follow_redirects=False).headers["location"] == "/dashboard"
      overview = client.get("/dashboard")
      devices = client.get("/dashboard/devices")
      projects = client.get("/dashboard/projects")

      assert 'data-dashboard-view="overview"' in overview.text
      assert 'id="device-status-table"' not in overview.text
      assert 'data-dashboard-view="devices"' in devices.text
      assert 'id="devices"' in devices.text
      assert 'data-dashboard-view="projects"' in projects.text
      assert 'id="new-project"' in projects.text
  ```

- [ ] **Step 2: Run the page tests and verify RED**

  ```text
  ..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py -q
  ```

  Expected: FAIL because only `/` exists and the template has anchor navigation/all content.

- [ ] **Step 3: Refactor the page handler without changing authentication**

  Keep the exact cookie lookup, `dev_auth_bypass`, `resolve_dashboard_user`, rejection cookie deletion, and no-store response behavior. Extract rendering after authentication and add the route handlers:

  ```python
  @router.get("/dashboard")
  async def dashboard_overview(request: Request) -> Response:
      return await render_dashboard_view(request, "overview")

  @router.get("/dashboard/devices")
  async def dashboard_devices(request: Request) -> Response:
      return await render_dashboard_view(request, "devices")

  @router.get("/dashboard/projects")
  async def dashboard_projects(request: Request) -> Response:
      return await render_dashboard_view(request, "projects")
  ```

  Make `/` call the same authorization helper and redirect only after successful identity resolution. Do not redirect unauthenticated callers through `/dashboard` merely to preserve a redirect chain.

- [ ] **Step 4: Make the template a view-aware semantic shell**

  Replace anchor sidebar links with route links. For each link, add `aria-current="page"` only when the Jinja `active_view` matches and a visually distinct active class. Add an `id="sidebar-toggle"` button with an explicit accessible label and tooltip text. Wrap view-specific sections in Jinja conditions so Overview has metrics/attention/projects/incidents, Devices has search/chips/table/pagination/drawer/Add Device, and Projects has project cards/New Project. Retain existing management dialog IDs on the routes where their JavaScript requires them.

  Use local inline SVG markup or safe DOM-built SVG icons for sidebar marks; do not add an icon dependency. Keep `{{ user_email }}` Jinja escaped.

- [ ] **Step 5: Run focused page tests and review rendered responses**

  ```text
  ..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py -q
  ..\.venv\Scripts\ruff.exe check --no-cache app tests
  ```

  Expected: all route/template assertions pass and Python static checks remain clean.

### Task 3: Implement view-aware rendering, sidebar preference, column filters, and cursor history

**Files:**

- Modify: `server/app/static/dashboard.js`
- Modify: `server/app/static/dashboard.css`
- Modify: `server/tests/test_dashboard_page.py`

**Interfaces:**

- `dashboardView` is read from the static template `data-dashboard-view` attribute and selects only that view's controller/listeners.
- Produces `cursorHistory: Array<string | null>`, `pageIndex: number`, `currentCursor(): string | null`, `resetDevicePagination(): void`, `nextDevicePage(): Promise<void>`, and `previousDevicePage(): Promise<void>`.
- Produces `applyDeviceFilter(name: "project_id" | "state" | "gpu_state", value: string): Promise<void>` and `clearDeviceFilters(): Promise<void>`; both reset cursor history before first-page request.
- Produces `setSidebarCollapsed(collapsed: boolean): void` using only the fixed preference key `skybeat.sidebar.v1` and values `collapsed`/`expanded`.

- [ ] **Step 1: Write failing static/controller source tests**

  Add assertions for route-specific view bootstrap, route query parsing for `project_id`, one fixed sidebar preference key, `aria-expanded` updates, popover Escape/focus restoration, filter chips, page size values 25/50/100, and opaque `cursorHistory`. Assert there is no `offset`, `WebSocket`, `EventSource`, `localStorage` key other than the sidebar preference, `sessionStorage`, `window.location.reload`, `innerHTML`, or chart/framework import.

  ```python
  def test_devices_uses_opaque_cursor_history_and_preserves_later_page_refresh() -> None:
      script = dashboard_script()

      assert "cursorHistory" in script
      assert "requestDevices(currentCursor())" in script
      assert "cursorHistory = [null]" in script
      assert "pageIndex = 0" in script
      assert "window.location.reload" not in script
      assert "offset" not in script.lower()
  ```

- [ ] **Step 2: Run static/dashboard tests and verify RED**

  ```text
  ..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py -q
  ```

  Expected: FAIL because the current script manages a single page with `nextCursor` and full-page filter form.

- [ ] **Step 3: Add guarded view bootstrap and safe shared utilities**

  Read the view from `document.body.dataset.dashboardView`. Resolve DOM nodes only inside the controller that owns them, so an Overview route never dereferences a Devices-only node. Keep common `element`, timestamp, status-pill, same-origin fetch, logout, and live-status utilities. Attach one listener per persistent control at startup; do not attach listeners while rendering rows or after polling.

  Add the sidebar control using:

  ```javascript
  const SIDEBAR_PREFERENCE_KEY = "skybeat.sidebar.v1";

  function setSidebarCollapsed(collapsed) {
    appShell.classList.toggle("sidebar-collapsed", collapsed);
    sidebarToggle.setAttribute("aria-expanded", String(!collapsed));
    localStorage.setItem(SIDEBAR_PREFERENCE_KEY, collapsed ? "collapsed" : "expanded");
  }
  ```

  Read only those two exact persisted values; remove/ignore invalid values. On narrow media queries, use the same control as an overlay drawer toggle and restore focus when it closes.

- [ ] **Step 4: Render the Overview and Projects views from bounded APIs**

  Render metric cards with differentiated token classes and text labels, a textual health bar whose accessible label includes `online`, `total`, and percentage (or `0 / 0 devices online` when total is zero), capped attention rows, compact project cards, and up to 10 existing incident rows. Each project link uses:

  ```javascript
  const target = new URL("/dashboard/devices", window.location.origin);
  target.searchParams.set("project_id", project.project_id);
  link.href = `${target.pathname}?${target.searchParams}`;
  ```

  The attention renderer presents `state`, `gpu_health.effective`, `has_active_incident`, and timestamp exactly as supplied; it must not assign a synthetic reason/severity or fetch device pages.

- [ ] **Step 5: Replace the standalone Devices form with accessible column-filter controls**

  Build Project, Availability, and GPU Health header buttons and small focus-contained popovers. Use existing API values: project UUID single selection; `ONLINE`, `SUSPECT`, `OFFLINE`, `AWAITING_FIRST_HEARTBEAT`; and the current accepted GPU values including `NOT_MONITORED`. Each selection calls `applyDeviceFilter`, closes its popover, returns focus to the owning button, resets `cursorHistory` to `[null]`, and loads page one. Escape closes without changing values.

  Render active filter chips with a labelled removal button. Search remains bounded/debounced and filters/page-size changes all call `resetDevicePagination`; do not store filter values outside the current URL/control state. Initialise the project filter from the canonical `project_id` query parameter only after validating it as a canonical UUID format.

- [ ] **Step 6: Replace Load More with opaque previous/next page history**

  Store only opaque cursors supplied by the server. The current-page request and next transition follow this shape:

  ```javascript
  function currentCursor() {
    return cursorHistory[pageIndex] ?? null;
  }

  async function nextDevicePage() {
    const payload = await requestDevices(currentCursor());
    if (typeof payload.next_cursor !== "string" || !payload.next_cursor) return;
    cursorHistory = cursorHistory.slice(0, pageIndex + 1);
    cursorHistory.push(payload.next_cursor);
    pageIndex += 1;
    await loadCurrentDevicePage();
  }

  async function previousDevicePage() {
    if (pageIndex === 0) return;
    pageIndex -= 1;
    await loadCurrentDevicePage();
  }
  ```

  Render only current-page rows and current response next state, preserve the scroll container's `scrollTop` while replacing its bounded tbody, and show `Page N` rather than a total-page claim. A refresh later calls `requestDevices(currentCursor())`; it does not truncate history/reset `pageIndex`. Retain existing rows and show stale/error state if the cursor request fails or returns an error. Provide an explicit first-page control for recovery; never manufacture a cursor.

- [ ] **Step 7: Preserve detail/history and management workflows on Devices**

  Keep detail abort/generation code, fixed history ranges/charts, Add Device, New Project from enrollment, credential clearing, project move, monitoring confirmation, and duplicate-submission flags. After a current-page refresh, call the existing controlled detail/history refresh when a drawer is open. Do not close it if the selected device is absent from the returned current page. Mutation success refreshes canonical Overview/Projects/Devices data for the relevant view without fabricating a row or resetting the sidebar.

- [ ] **Step 8: Implement the refined local CSS system**

  Consolidate dashboard custom properties for navy shell, cool-slate workspace, blue accent, emerald, amber, coral/red, cyan/indigo GPU accent, type scale, border, shadow, and spacing. Add styles for expanded/collapsed/drawer sidebar, active nav, metric status variants, accessible health bar, attention/project/incident rows, dense sticky device header, horizontal table workspace, filter popovers/chips, page controls, dialogs/drawer, visible focus, and responsive breakpoints. Add a `prefers-reduced-motion: reduce` block disabling any metric emphasis/transition.

- [ ] **Step 9: Run source/static tests and format checks**

  ```text
  ..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py -q
  ..\.venv\Scripts\ruff.exe check --no-cache app tests
  ..\.venv\Scripts\ruff.exe format --check app tests
  ```

  Expected: source guards prove safe DOM/no new transport or framework, and all existing drawer/history/management checks remain valid or are deliberately updated for explicit routes.

### Task 4: Make page-specific automatic refresh failure-safe and verify regressions

**Files:**

- Modify: `server/app/static/dashboard.js`
- Modify: `server/tests/test_dashboard_page.py`
- Modify: `server/tests/test_dashboard_api.py`

**Interfaces:**

- Produces `refreshActiveView(): Promise<void>` that dispatches by `dashboardView` and refuses overlap through one in-flight boolean.
- Overview refreshes overview plus the existing bounded incidents request; Devices refreshes its exact current cursor page plus project data for controls; Projects refreshes the existing project list.
- `scheduleRefresh()` uses `document.hidden ? 60000 : 15000` and exactly one timeout, not an interval.

- [ ] **Step 1: Write failing refresh-state tests**

  Add static assertions that a single active-view dispatcher uses `Promise.allSettled`, calls no device request for Overview/Projects, preserves `currentCursor()` in Device refresh, refreshes an open detail without closing it, contains one timeout scheduler, and changes the readable indicator between live and stale states. Assert prohibited transports remain absent.

  ```python
  def test_active_view_refresh_is_non_overlapping_and_later_page_safe() -> None:
      script = dashboard_script()

      assert "async function refreshActiveView()" in script
      assert "if (refreshing) return" in script
      assert 'document.hidden ? 60000 : 15000' in script
      assert "requestDevices(currentCursor())" in script
      assert "WebSocket" not in script
      assert "EventSource" not in script
  ```

- [ ] **Step 2: Run refresh tests and verify RED**

  ```text
  ..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py tests/test_dashboard_api.py -q
  ```

  Expected: FAIL because the current single-page `refreshDashboard` always requests Overview and Devices.

- [ ] **Step 3: Implement active-view polling without page reload or overlapping requests**

  Replace the single-page refresh routine with `refreshActiveView`. It must clear and set the existing timeout once, exit when already refreshing, use `Promise.allSettled` for the bounded requests relevant to the current view, retain successful DOM portions if another request fails, and call `refreshOpenDetail`/`refreshOpenHistory` only when the Devices drawer is open. On a later Devices page, capture its current cursor and `pageIndex` before the request; apply the response only if the captured cursor/page still matches current state, preventing a delayed result from overwriting a newer filter/page selection.

  Render `Live updates · updated …` after a full relevant success and `Data stale · last updated …` after any relevant failure. Preserve the exact timestamp in `title` and use a polite live region. Do not claim socket connectivity.

- [ ] **Step 4: Run targeted dashboard regressions**

  ```text
  ..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py tests/test_dashboard_api.py tests/test_dashboard_read.py tests/test_dashboard_stage07_read.py tests/test_dashboard_management.py -q
  ```

  Expected: route/API/read/static management and refresh regressions pass.

### Task 5: Complete verification, status checkpoint, and browser-acceptance handoff

**Files:**

- Modify: `docs/IMPLEMENTATION_STATUS.md`
- Inspect: all Stage 07.6B changed files and existing dirty worktree entries

**Interfaces:**

- Produces a factual Stage 07.6B status section stating `IMPLEMENTED / AWAITING BROWSER ACCEPTANCE` only after all executable checks below succeed.
- Does not alter the Stage 07 overall completion status or claim real-browser acceptance.

- [ ] **Step 1: Run focused and full server verification**

  From `server`, run:

  ```text
  ..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py tests/test_dashboard_api.py tests/test_dashboard_read.py tests/test_dashboard_stage07_read.py tests/test_dashboard_management.py -q
  ..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q
  ..\.venv\Scripts\ruff.exe check --no-cache app tests
  ..\.venv\Scripts\ruff.exe format --check app tests
  ..\.venv\Scripts\mypy.exe app --strict --cache-dir D:\skybeat\.stage07-6b-final-mypy-cache
  ```

  Expected: all non-environment-dependent server tests pass; any skipped real-MySQL tests are reported exactly as skipped and are not counted as proof.

- [ ] **Step 2: Run migration/deployment/diff safety checks**

  From the repository root, run:

  ```text
  .\.venv\Scripts\python.exe -m alembic -c server\alembic.ini heads
  .\.venv\Scripts\python.exe -m alembic -c server\alembic.ini history
  .\.venv\Scripts\python.exe scripts\validate_deployment.py
  git diff --check
  git status --short
  ```

  Expected: existing sole Alembic head remains unchanged, deployment validator passes, diff has no whitespace error, and status contains only intentional worktree changes. If the existing virtual-environment path differs, use the repository's established Python command rather than creating a new environment.

- [ ] **Step 3: Inspect security and scope boundaries**

  Search the final static/template files for prohibited strings and inspect the result:

  ```text
  rg -n "WebSocket|EventSource|innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|sessionStorage|window\.location\.reload|offset" server/app/static/dashboard.js server/app/templates/dashboard.html
  rg -n "localStorage" server/app/static/dashboard.js
  ```

  Expected: no prohibited feature/use; only `skybeat.sidebar.v1` local preference storage is present. Confirm no migration was created and no Stage 08 feature appears.

- [ ] **Step 4: Update the implementation checkpoint only with evidence**

  Add Stage 07.6B files changed, exact passing/failing/skipped command counts, no-migration/no-WebSocket/SSE confirmation, security notes, unresolved real-MySQL/browser limitations, and this exact manual acceptance list:

  1. Sign in and verify `/` lands on `/dashboard`; verify all three nav routes and active state.
  2. Collapse/expand the sidebar, reload, and verify only the visual preference persists; verify narrow overlay keyboard/focus behavior.
  3. Inspect Overview metric meter, capped attention ordering, compact projects, incidents, live and stale states.
  4. On Devices, use search and every column filter by keyboard; verify chips/Clear all and project links reset cursors safely.
  5. Move to a later keyset page, wait for auto-refresh, and verify page position, filters, scroll, drawer, and history remain intact.
  6. Verify Add Device, one-time credential copy/close clearing, New Project, project reassignment, and enable/disable confirmation.
  7. Check desktop and narrow layouts, sticky device header, horizontal table use, focus visibility, and reduced-motion behavior.
  8. Capture requested screenshots before accepting Stage 07.6B; leave overall Stage 07 open.

- [ ] **Step 5: Do not commit or push**

  Report `git status --short` in the final implementation handoff. Do not create a commit, push, deployment, provider call, or destructive database operation unless a later explicit user instruction authorizes it.

## Plan self-review

- **Spec coverage:** Task 1 covers the only backend addition and its cap/order/canonical constraints. Task 2 covers the three routes/shared shell. Task 3 covers visual hierarchy, responsive navigation, table filters, cursor history, management/detail retention, and styling. Task 4 covers all automatic polling and stale behavior. Task 5 covers verification, status, and browser acceptance.
- **No placeholders:** All task files, interfaces, test cases, commands, explicit bounds, prohibited features, and manual acceptance steps are specified. There are no deferred implementation markers.
- **Type consistency:** `ATTENTION_LIMIT`, `_attention_view`, `DashboardReadService.overview`, `dashboardView`, `cursorHistory`, `pageIndex`, `currentCursor`, and `refreshActiveView` use the same names throughout.
- **Review focus ownership:** The five high-risk conditions listed above are covered by Tasks 1, 3, and 4 respectively.
