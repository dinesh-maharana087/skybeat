# Stage 07.4 Operational Device Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe, responsive selected-device diagnostic panel with complete canonical detail and bounded recent incident visibility.

**Architecture:** Preserve the Stage 07.3 single Jinja page and vanilla-JavaScript dashboard. Add only a backward-compatible optional `device_id` filter to the existing authorized, bounded incident list; the drawer requests canonical device detail and that bounded filtered incident projection, never reconstructs detail from the table, and never reads history.

**Tech Stack:** FastAPI, SQLAlchemy 2, Jinja2, vanilla JavaScript DOM APIs, CSS, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-23-stage07-dashboard-runbook-design.md`; `C:\Users\mahar\.codex\attachments\f2264a2b-e4b5-4c98-ac45-da997718f819\Pasted text.txt`

## Global Constraints

- Implement Stage 07.4 only; do not implement Stage 07.5 history requests, charts, SVG/canvas graphing, or a frontend framework.
- `GET /api/v1/incidents?device_id=<canonical-device-uuid>` is the explicitly approved backward-compatible correction. It keeps current dashboard authorization, no-store, limit 1–100/default 50, newest-first keyset ordering, opaque cursor behavior, and display-safe incident projection.
- The optional incident filter must be applied in server SQL before `limit + 1`; browser-side filtering of global incidents and unbounded incident requests are prohibited.
- Do not alter availability, GPU-health, heartbeat, incident lifecycle, notification, authentication/session, CSP, or database schema behavior; no migration.
- All dynamic values use `createElement`, `textContent`, and safe property/attribute assignments. No raw JSON rendering, `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, inline handlers, browser credential storage, console logging, or remote scripts.
- Device detail comes only from `GET /api/v1/devices/{device_uuid}`, never from table row telemetry. Incidents come only from the bounded filtered incident endpoint.
- Detail refresh participates only in the existing visible 15-second/hidden 60-second dashboard cycle. No independent detail timer, no history request, and no client inference of device or GPU health.
- No commit, push, dependency, MySQL ACL/data action, production operation, or destructive action.

## Review Focus

- A malformed device incident filter must be rejected safely and a valid filter must not leak another device’s incidents; Task 1 owns route/service tests.
- A late Device A response after Device B is selected must not overwrite Device B; Task 3 owns a generation/abort static-behavior test.
- Detail refresh failure after success must retain previous detail and mark it stale; Task 3 owns that contract.
- Sparse/null storage and GPU fields, including multiple GPUs, must show `—` rather than fabricated zero values; Task 3 owns rendering tests.
- Stage 07.5 must remain absent: no `/history`, chart API, SVG/canvas chart, or raw JSON output; Task 4 owns the scope guard.

---

### Task 1: Bounded canonical per-device incident filter

**Files:**
- Modify: `server/app/dashboard/read.py`
- Modify: `server/app/api/dashboard.py`
- Modify: `server/tests/test_dashboard_api.py`
- Modify: `server/tests/test_dashboard_stage07_read.py`
- Modify: `docs/API_SPEC.md`

**Interfaces:**
- Produces `DashboardReadService.list_incidents(*, limit: int = 50, cursor: str | None = None, device_id: str | None = None) -> dict[str, object]`.
- Extends `GET /api/v1/incidents` with optional `device_id` (canonical device UUID) while preserving requests without it byte-for-byte at the projection level.
- Consumes existing `_incident_view`, `Device.device_uuid`, incident cursor codec, and dashboard authorization dependency.

- [x] **Step 1: Write failing endpoint and projection tests**

```python
def test_authorized_incident_filter_forwards_only_a_bounded_device_id():
    class DashboardRead:
        def list_incidents(self, *, limit, cursor, device_id):
            assert (limit, cursor, device_id) == (25, "opaque", DEVICE_UUID)
            return {"items": [], "next_cursor": None, "server_time": "2026-09-23T10:00:00Z"}

    response = authorized_client(DashboardRead()).get(
        f"/api/v1/incidents?limit=25&cursor=opaque&device_id={DEVICE_UUID}"
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_incident_filter_is_applied_before_limit_plus_one(monkeypatch):
    statement = captured_incident_statement_for(device_id=DEVICE_UUID)
    assert "devices.device_uuid" in str(statement)
    assert statement._limit_clause.value == 51
```

- [x] **Step 2: Run the targeted tests to verify RED**

Run from `server`:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_api.py tests/test_dashboard_stage07_read.py -q
```

Expected: FAIL because `list_incidents` and the route do not yet accept or apply `device_id`.

- [x] **Step 3: Add the optional bounded server filter**

```python
def list_incidents(
    self, *, limit: int = 50, cursor: str | None = None, device_id: str | None = None
) -> dict[str, object]:
    # Keep the existing ordered Incident -> Device -> Project projection.
    # When device_id is present, validate it with the existing canonical UUID
    # boundary and add Device.device_uuid == device_id before cursor and limit+1.
    if device_id is not None:
        statement = statement.where(Device.device_uuid == _uuid(device_id))
```

Add `device_id: str | None = Query(default=None, max_length=36)` to the incidents route and pass it through `asyncio.to_thread`. Convert the existing canonical UUID rejection into the established safe dashboard-query 422 response, preserving 401/no-store behavior. Do not add a new endpoint, change ordering, change cursor format, expose event/delivery data, or verify device existence separately; a valid unknown UUID simply has an empty bounded result.

Document the optional filter in the existing `GET /api/v1/incidents` contract, including that it is applied server-side before pagination and returns the same display-safe incident projection.

- [x] **Step 4: Run targeted API/read regressions to verify GREEN**

Run:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_api.py tests/test_dashboard_stage07_read.py tests/test_dashboard_read.py -q
```

Expected: PASS; unfiltered incident behavior and Stage 07.2 no-store/auth boundaries remain compatible.

### Task 2: Accessible detail drawer shell and selection boundary

**Files:**
- Modify: `server/app/templates/dashboard.html`
- Modify: `server/app/static/dashboard.css`
- Modify: `server/tests/test_dashboard_page.py`

**Interfaces:**
- Produces a non-modal complementary detail drawer with IDs consumed by the dashboard script: `detail-panel`, `detail-title`, `detail-status`, `detail-content`, `detail-incidents`, `detail-retry`, and `detail-close`.
- Consumes existing device-name table actions and preserves the main table/dashboard visibility.

- [x] **Step 1: Write a failing page-shell test**

```python
def test_dashboard_page_contains_accessible_device_detail_drawer():
    response = authenticated_dashboard_response()
    assert 'id="detail-panel"' in response.text
    assert 'aria-labelledby="detail-title"' in response.text
    assert 'id="detail-close"' in response.text
    assert 'id="detail-retry"' in response.text
    assert 'id="detail-incidents"' in response.text
```

- [x] **Step 2: Run the page test to verify RED**

Run:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py -q
```

Expected: FAIL because Stage 07.3 still has the legacy raw-detail section.

- [x] **Step 3: Replace the legacy raw-detail surface with a non-modal drawer**

Use an `aside` with `role="complementary"`, `hidden` initially, a labelled title, `aria-live` detail status, explicit Close and Retry buttons, and discrete identity/freshness/system/storage/GPU/policy/incident containers. Keep it non-modal so the operational table remains available. Device-name buttons stay keyboard accessible and call a dedicated `openDetail(deviceId, originButton)` function through an event listener; do not attach device data to markup attributes or inline JavaScript.

Add responsive CSS that positions the drawer at the right on wide screens without covering the whole page, stacks it full-width on narrow screens, wraps long UUID/hostname/model values, and preserves focus indication and textual state/error markers.

- [x] **Step 4: Run the page test to verify GREEN**

Run:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py -q
```

Expected: PASS with existing authorization, escaping, and Stage 07.3 shell tests.

### Task 3: Canonical detail/incident rendering, race control, and refresh handling

**Files:**
- Modify: `server/app/static/dashboard.js`
- Modify: `server/app/static/dashboard.css`
- Modify: `server/tests/test_dashboard_page.py`

**Interfaces:**
- Consumes canonical `GET /api/v1/devices/{device_uuid}` and bounded `GET /api/v1/incidents?device_id={device_uuid}&limit=50` responses.
- Produces `openDetail(deviceId, origin)`, `refreshOpenDetail()`, `closeDetail()`, safe detail section renderers, and detail request generation/abort state.

- [x] **Step 1: Write failing static UI safety/lifecycle tests**

```python
def test_dashboard_detail_uses_canonical_bounded_endpoints_with_race_and_scope_guards():
    script = dashboard_script()
    assert 'fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}`' in script
    assert 'query.set("device_id", deviceId)' in script
    assert 'const detailGeneration' in script or 'let detailGeneration' in script
    assert "AbortController" in script
    assert "refreshOpenDetail" in script
    assert "/history" not in script
    assert "JSON.stringify" not in script
    for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert unsafe not in script
```

- [x] **Step 2: Run the detail tests to verify RED**

Run:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py -q
```

Expected: FAIL because the current detail action reads legacy alerts and displays raw JSON.

- [x] **Step 3: Implement safe detail behavior**

Maintain `selectedDeviceId`, `detailGeneration`, `detailAbortController`, `detailLastSuccess`, and `detailOrigin`. `openDetail` increments the generation, aborts any previous detail request, opens/focuses the panel, renders loading, then fetches the canonical detail and incidents in parallel. Apply results only when the generation and selected UUID still match; a late prior request cannot update the panel.

Render labelled sections using only `textContent` and `createElement`:

```javascript
const detail = await requestDeviceDetail(deviceId, signal);
const incidents = await requestDeviceIncidents(deviceId, signal);
renderIdentity(detail);       // name, UUID, project, enabled, state, effective GPU state
renderFreshness(detail);      // latest receipt, last seen, telemetry_stale
renderSystem(detail);         // hostname, IPs, OS, agent version, uptime, CPU, memory
renderStorage(detail.disks);  // canonical fields only; empty => “No storage telemetry available.”
renderGpus(detail.gpus);      // every canonical GPU, sparse values => “—”
renderExpectedPolicy(detail.expected_gpu_policy);
renderIncidents(incidents.items);
```

Use display-only byte/percentage/temperature formatters that preserve null as `—` and numeric zero as `0`; do not derive device/GPU health, expected-inventory mismatch, or storage health. Detail and incident failures are independent: retain successful detail when incidents fail, retain prior successful detail on refresh failure with a stale marker, and provide Retry for an initial failure. Close hides the panel, aborts the pending request, clears selected state, and returns focus to the originating device button; Escape closes when the drawer is open.

At the end of a successful normal `refreshDashboard` cycle, call `refreshOpenDetail()` once if a device is selected. It reuses the current non-overlapping dashboard cycle; it creates no timer and does not request `/history`.

- [x] **Step 4: Run focused UI/API/read tests to verify GREEN**

Run:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py tests/test_dashboard_api.py tests/test_dashboard_stage07_read.py tests/test_dashboard_read.py -q
```

Expected: PASS. Existing Stage 07.3 polling/filter/pagination behavior remains intact and Stage 07.2 APIs stay bounded and authorized.

### Task 4: Acceptance checkpoint and final verification

**Files:**
- Modify: `docs/IMPLEMENTATION_STATUS.md`
- Test: `server/tests/test_dashboard_page.py`

**Interfaces:**
- Consumes Tasks 1–3 evidence.
- Produces a Stage 07.4 COMPLETE / ACCEPTED checkpoint while retaining Stage 07 IN PROGRESS and Stage 07.5 not started.

- [x] **Step 1: Add a scope-completion guard**

```python
def test_dashboard_detail_excludes_history_charts_and_raw_json():
    script = dashboard_script()
    assert "/history" not in script
    assert "JSON.stringify" not in script
    assert "createElement(\"svg\")" not in script
    assert "createElement(\"canvas\")" not in script
```

- [x] **Step 2: Run the guard to verify RED or confirm an earlier task already made it GREEN**

Run:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py -q
```

Expected: PASS after Task 3; retain it as the Stage 07.5 scope boundary.

- [x] **Step 3: Update documentation/status only after evidence**

Document the optional bounded `device_id` incident filter in `docs/API_SPEC.md`. After all executable checks pass, update `docs/IMPLEMENTATION_STATUS.md`: mark Stage 07.4 COMPLETE / ACCEPTED, retain Stage 07 IN PROGRESS, state that Stage 07.5 is not started, record exact results/no migration/unchanged availability-GPU semantics, preserve real-MySQL and browser/Linux/Docker pending evidence, and remove the resolved Stage 07.4 API-decision blocker.

- [x] **Step 4: Run final verification**

Run from `server`:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py tests/test_dashboard_api.py tests/test_dashboard_stage07_read.py tests/test_dashboard_read.py -q
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q
..\.venv\Scripts\ruff.exe check --no-cache app tests migrations ..\scripts
..\.venv\Scripts\ruff.exe format --check --no-cache app tests migrations ..\scripts
..\.venv\Scripts\mypy.exe app --strict --cache-dir D:\skybeat\.stage07-4-mypy-cache
..\.venv\Scripts\python.exe -m alembic heads
..\.venv\Scripts\python.exe -m alembic history
..\.venv\Scripts\python.exe ..\scripts\validate_deployment.py
git -C .. diff --check
```

Do not rerun the agent suite: this stage changes only dashboard server/read/UI/test/docs files and does not alter agent code, heartbeat schemas, or deployment artifacts. State that decision in the checkpoint.

Expected: all executable server checks pass. The unavailable isolated MySQL and Bash checks remain explicitly skipped; browser execution remains environment-pending without adding a heavy framework.

## Plan Self-Review

- Spec coverage: Task 1 resolves the only approved API blocker while retaining its bounded/read-only contract; Task 2 creates the accessible non-modal detail structure; Task 3 owns canonical detail rendering, incidents, race control, refresh, failure behavior, and responsive presentation; Task 4 locks the no-history boundary and records evidence.
- Placeholder scan: no unbounded incident collection, event/delivery data, raw telemetry, chart behavior, lifecycle change, schema change, or client-side health rule is unspecified.
- Type consistency: the route/filter uses `device_id` end-to-end; `openDetail` and `refreshOpenDetail` are the only selection/refresh entry points; Stage 07.2 response field names are those returned by `device_view` and `_incident_view`.
- Review focus: malformed/cross-device filter behavior, stale response races, failed refresh retention, sparse GPU/storage telemetry, and Stage 07.5 scope each have an owning test task.
