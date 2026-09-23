# Stage 07.3 Operational Dashboard UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the authenticated SkyBeat Device Status page into the bounded operational monitoring console defined for Stage 07.3.

**Architecture:** Keep the existing server-rendered Jinja entry page and make same-origin vanilla JavaScript consume the accepted Stage 07.2 overview and device-list projections. The browser owns only presentation, filters, opaque cursor forwarding, and refresh freshness; the server remains authoritative for availability, GPU health, telemetry freshness, incidents, and all counts.

**Tech Stack:** Jinja2, vanilla JavaScript DOM APIs, CSS, FastAPI TestClient/static-asset tests, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-23-stage07-dashboard-runbook-design.md`; `C:\Users\mahar\.codex\attachments\8bb55ca8-68fc-436d-a2d4-f8eff4307129\Pasted text.txt`

## Global Constraints

- Implement Stage 07.3 only; do not implement the Stage 07.4 device-detail expansion or Stage 07.5 history visualizations.
- Do not change Stage 07.2 API contracts, heartbeat, availability, GPU-health, incident, authentication, session, CSP, or schema behavior.
- Use only same-origin `fetch`, `createElement`, `replaceChildren`, `textContent`, and safe attribute/property assignment for dynamic data; never use `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `eval`, inline handlers, browser credential storage, remote scripts, or client-side state/GPU calculations.
- Preserve `Cache-Control: no-store`, Google OIDC authorization, opaque secure cookies, logout behavior, and the restrictive existing CSP.
- Device pagination uses the server cursor as an opaque value. The UI page limit is 50 and never exceeds the API maximum of 100.
- Visible polling is 15 seconds, hidden polling is 60 seconds, and polling replaces the first device page rather than merging or appending it.
- No dependency, migration, database/ACL modification, production operation, commit, or push.

## Review Focus

- API-controlled strings, including hostile names and future status values, must reach the DOM only through `textContent`; Task 2 owns the static safety test.
- Browser refresh failures must retain existing sections and the last successful timestamp; Task 3 owns this behavior and its static guard.
- Filter changes must clear the opaque cursor and replace rows rather than append stale pages; Task 3 owns the filter and pagination tests.
- Device availability and GPU health must display server values and never be inferred from metrics; Task 2 owns the source-level checks.
- Visibility changes and overlapping fetches must not accumulate timers or create duplicate requests; Task 3 owns the polling checks.

---

### Task 1: Semantic operational dashboard shell

**Files:**
- Modify: `server/app/templates/dashboard.html`
- Modify: `server/tests/test_dashboard_page.py`

**Interfaces:**
- Produces stable DOM IDs consumed by `dashboard.js`: `last-refresh`, `dashboard-stale-warning`, `overview-cards`, `project-summary`, `project-filter`, `state-filter`, `gpu-state-filter`, `search`, `include-disabled`, `reset-filters`, `devices`, `device-empty`, `device-error`, `load-more`.
- Consumes the existing escaped `user_email` template value and existing `/auth/logout` action.

- [ ] **Step 1: Write failing page-shell tests**

```python
def test_dashboard_page_contains_operational_sections_and_accessible_controls():
    response = authenticated_dashboard_response()
    assert 'id="overview-cards"' in response.text
    assert 'id="project-summary"' in response.text
    assert 'id="project-filter"' in response.text
    assert 'id="gpu-state-filter"' in response.text
    assert 'id="dashboard-stale-warning"' in response.text
    assert 'id="last-refresh"' in response.text
    assert 'id="load-more"' in response.text
```

- [ ] **Step 2: Run the focused page test to verify RED**

Run from `server`:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py -q
```

Expected: FAIL because the current template contains only legacy search/state controls and no operational sections.

- [ ] **Step 3: Build the static semantic page structure**

Replace the minimal page body with a semantic header, refresh metadata, six named overview-card containers plus an explicit awaiting-first-heartbeat count, a compact project-summary section, labelled filter form controls, an operational table container, and separate loading/empty/error/stale/live regions. Keep the Jinja identity interpolation in ordinary escaped template text and retain the external deferred script/style references.

```html
<p id="last-refresh" aria-live="polite">Last successful refresh: not yet available.</p>
<p id="dashboard-stale-warning" role="status" hidden>
  Dashboard data may be stale — refresh failed.
</p>
<section id="overview-cards" aria-label="Current device overview"></section>
<section id="project-summary" aria-labelledby="project-summary-heading"></section>
<form id="filters" novalidate>...</form>
<section class="device-table-region" aria-labelledby="device-status-heading">
  <div id="devices" aria-live="polite"></div>
  <p id="device-empty" hidden></p>
  <p id="device-error" role="alert" hidden></p>
  <button id="load-more" type="button" hidden>Load more devices</button>
</section>
```

Do not add a device detail panel, history control, chart container, token-bearing field, or inline event handler. The legacy detail behavior may remain only if it continues to use the existing protected routes without expansion.

- [ ] **Step 4: Run focused page tests to verify GREEN**

Run:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py -q
```

Expected: PASS, including unauthenticated redirect, escaped identity, no-store response, and the new structural assertions.

### Task 2: Safe operational projection rendering and responsive styling

**Files:**
- Modify: `server/app/static/dashboard.js`
- Modify: `server/app/static/dashboard.css`
- Modify: `server/tests/test_dashboard_page.py`

**Interfaces:**
- Consumes accepted `GET /api/v1/dashboard/overview` payloads with `counts`, `projects`, `projects_truncated`, and `server_time`.
- Consumes accepted `GET /api/v1/devices` payloads with `items`, `next_cursor`, and `server_time`.
- Produces `renderOverview(payload)`, `renderProjects(payload)`, `renderDevices(items, {append})`, and safe display helpers for server values.

- [ ] **Step 1: Write failing static-rendering tests**

```python
def test_dashboard_script_renders_stage07_2_values_without_unsafe_html_or_client_state_rules():
    script = dashboard_script()
    assert '"GPU Problems"' in script
    assert '"Active Incidents"' in script
    assert '"AWAITING_FIRST_HEARTBEAT"' in script
    assert 'item.state' in script
    assert 'item.gpu_health?.effective' in script
    assert 'innerHTML' not in script
    assert 'outerHTML' not in script
    assert 'insertAdjacentHTML' not in script
    assert 'eval(' not in script
```

- [ ] **Step 2: Run the script/page tests to verify RED**

Run:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py -q
```

Expected: FAIL because overview/project rendering and the complete operational projection do not exist.

- [ ] **Step 3: Implement DOM-only renderers and status-safe CSS**

Implement one `element(tag, text)` helper that calls `document.createElement` and assigns `textContent`, a `displayValue` helper that returns `—` only for null/undefined/empty values, and `formatPercent` that adds `%` only to finite numeric values. Render six labelled overview cards directly from `payload.counts`, display awaiting-first-heartbeat separately, and render project names/counts supplied by the API without deriving any state.

Render device rows with the required columns: Project, Device, Hostname, Availability, Last Seen, CPU, Memory, GPU Health, GPU Count, Primary IP, Agent Version, Latest Telemetry. Use `item.state`, `item.gpu_health?.effective`, `item.telemetry_stale`, and supplied timestamps verbatim as display inputs. Unknown and absent values use `—`; numeric zero remains `0` or `0%`. Future states are shown as received text.

Use a table wrapper with horizontal overflow, responsive card/filter grid rules, status classes as supplemental visual reinforcement, visible keyboard focus, sufficient contrast, and narrow-viewport wrapping. Do not use animations, gradients, a CSS framework, generated HTML strings, or a chart style/component.

- [ ] **Step 4: Run static rendering tests to verify GREEN**

Run:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py tests/test_dashboard_read.py -q
```

Expected: PASS; existing null-versus-zero read projection behavior remains unchanged.

### Task 3: Bounded filtering, opaque pagination, and refresh lifecycle

**Files:**
- Modify: `server/app/static/dashboard.js`
- Modify: `server/tests/test_dashboard_page.py`

**Interfaces:**
- Consumes filter values accepted by Stage 07.2: project UUID, canonical availability values, canonical GPU values, search, `include_disabled`, and opaque `cursor`.
- Produces `reloadDevices()`, `loadMoreDevices()`, `refreshDashboard()`, `scheduleRefresh()`, and a one-request-at-a-time dashboard lifecycle.

- [ ] **Step 1: Write failing lifecycle/static contract tests**

```python
def test_dashboard_script_uses_opaque_cursor_safe_polling_and_stale_retention():
    script = dashboard_script()
    assert 'const PAGE_LIMIT = 50' in script
    assert 'nextCursor' in script
    assert 'query.set("cursor", nextCursor)' in script
    assert 'document.hidden ? 60000 : 15000' in script
    assert 'document.addEventListener("visibilitychange"' in script
    assert 'if (refreshing) return' in script
    assert 'Dashboard data may be stale' in script
    assert 'decode' not in script.lower()
```

- [ ] **Step 2: Run the lifecycle test to verify RED**

Run:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py -q
```

Expected: FAIL because the current page has no project/GPU/disabled filtering, opaque paging, or complete polling strategy.

- [ ] **Step 3: Implement deterministic UI request state**

Keep `nextCursor` as an opaque string and never decode/log/transform it. A filter form submission or Reset filters clears `nextCursor`, clears displayed rows, and requests the first page. Use a 250 ms debounce for search input; select/checkbox changes submit the same reset path. Query only accepted parameter names and omit empty filters.

Use a `loadingDevices` guard for page fetches and a `refreshing` guard for overview/list refreshes. `Load more` forwards the opaque cursor, appends only that page on success, and hides/disables itself when `next_cursor` is null. Periodic refresh calls overview and a first-page device request, then replaces rows and resets the cursor; it never appends. Schedule exactly one next timer in `finally`, clear the old timer before scheduling, choose 15 seconds visible/60 seconds hidden, and trigger one safe refresh on visibility return.

On independent overview/device failure, retain that section’s previous successful DOM; update the visible stale-warning text without exposing server error details, retain `last-refresh`, and clear the warning only after a later complete successful refresh. Preserve distinct initial-loading, no-system-devices, no-filter-match, and safe error messages.

- [ ] **Step 4: Run focused dashboard UI/API regressions to verify GREEN**

Run:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py tests/test_dashboard_api.py tests/test_dashboard_stage07_read.py tests/test_dashboard_read.py -q
```

Expected: PASS. The API tests prove the Stage 07.2 endpoint/auth/no-store boundary remains unchanged; page tests pin the static UI safety and lifecycle contract.

### Task 4: Documentation checkpoint and final Stage 07.3 verification

**Files:**
- Modify: `docs/IMPLEMENTATION_STATUS.md`
- Test: `server/tests/test_dashboard_page.py`

**Interfaces:**
- Consumes completed Stage 07.3 assets and final executable evidence.
- Produces an accurate Stage 07.3 COMPLETE / ACCEPTED checkpoint that preserves Stage 07 as IN PROGRESS and marks Stages 07.4/07.5 pending.

- [ ] **Step 1: Write the failing completion invariant**

```python
def test_dashboard_page_documents_stage07_3_operational_ui_contract():
    page = dashboard_template()
    assert 'SkyBeat Device Status' in page
    assert 'overview-cards' in page
    assert 'load-more' in page
```

- [ ] **Step 2: Run the focused test to verify RED or confirm Task 1 already made it GREEN**

Run:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py -q
```

Expected: PASS after Task 1; this is the checkpoint invariant used before status acceptance.

- [ ] **Step 3: Update the factual implementation checkpoint after successful verification**

Update `docs/IMPLEMENTATION_STATUS.md` only after all listed executable checks pass. Mark Stage 07.3 COMPLETE / ACCEPTED while retaining Stage 07 IN PROGRESS; record the UI behavior, exact fresh results, no migration, unchanged Stage 07.2 contracts, existing MySQL/Bash/Linux/Docker pending items, and the exact next work as Stage 07.4 device-detail expansion followed by Stage 07.5 history visualization. Do not claim browser, real-MySQL, Linux, Docker, Caddy, or production evidence that did not run.

- [ ] **Step 4: Run final verification**

Run from `server`:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py tests/test_dashboard_api.py tests/test_dashboard_stage07_read.py tests/test_dashboard_read.py -q
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q
..\.venv\Scripts\ruff.exe check --no-cache app tests migrations ..\scripts
..\.venv\Scripts\ruff.exe format --check --no-cache app tests migrations ..\scripts
..\.venv\Scripts\mypy.exe app --strict --cache-dir D:\skybeat\.stage07-3-mypy-cache
..\.venv\Scripts\python.exe -m alembic heads
..\.venv\Scripts\python.exe -m alembic history
..\.venv\Scripts\python.exe ..\scripts\validate_deployment.py
git -C .. diff --check
```

Do not run the agent suite because Stage 07.3 modifies only server dashboard presentation assets/tests and does not touch agent code, shared heartbeat contracts, or deployment artifacts. Record that decision in the checkpoint.

Expected: all local server tests and static/type/migration/deployment/diff checks pass; only the already documented isolated-MySQL and Bash environment skips remain.

## Plan Self-Review

- Spec coverage: Task 1 supplies the accessible static shell; Task 2 renders every accepted Stage 07.2 overview/device field with responsive safe presentation; Task 3 owns filters, opaque paging, polling, loading/stale/error behavior; Task 4 records acceptance evidence without crossing into detail/history scope.
- Placeholder scan: no API change, inferred state, dynamic HTML, unbounded request, external dependency, migration, browser storage, device-detail expansion, or chart behavior is left unspecified.
- Type consistency: the template IDs named by Task 1 are exactly the DOM dependencies in Tasks 2-3; both endpoint payload shapes are already defined in Stage 07.2 and remain unchanged.
- Review focus: DOM injection, stale retention, filter/cursor reset, server-authoritative status, and non-overlapping visibility-aware polling each have a named owning task and test.

