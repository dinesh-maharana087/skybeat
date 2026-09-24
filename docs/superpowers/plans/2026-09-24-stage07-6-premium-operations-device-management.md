# Stage 07.6 Premium Operations UI and Device Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the existing authenticated operational dashboard and add safe, minimal project creation, device enrollment, project reassignment, and monitoring enable/disable workflows without changing SkyBeat monitoring semantics or the Stage 04 authentication model.

**Architecture:** Keep the one server-rendered Jinja dashboard and same-origin vanilla JavaScript. Add authenticated JSON mutation routes behind the established `dashboard_user` dependency, route each mutation through the existing canonical `IdentityService`, and return bounded display projections rather than ORM objects. The dashboard uses dialogs and explicit confirmations, refreshes existing canonical read projections after each success, and holds a generated enrollment credential only in transient JavaScript/DOM state until dismissed.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy 2, existing `IdentityService`, Jinja2, vanilla JavaScript DOM/SVG APIs, CSS, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-24-stage07-6-premium-operations-device-management-design.md`

## Global Constraints

- Implement Stage 07.6 only. Do not begin Stage 08, add a migration, alter heartbeat schemas, or change availability, GPU-health, incidents, events, notification, authentication, session, OIDC, CSP, or history API semantics.
- Preserve the existing authenticated dashboard/page/API dependency boundary. The local-development bypass, when explicitly enabled, works only because it resolves the same `DashboardUser`; do not add an unprotected route or a second authorization model.
- All dashboard mutations must require the existing authenticated dashboard identity, pass the existing same-origin mutation check, return `Cache-Control: no-store`, validate bounded JSON input, and return safe structured errors without echoing credentials.
- Reuse canonical `IdentityService.create_project`, `IdentityService.enroll`, `IdentityService.move`, and `IdentityService.set_enabled`. Do not duplicate validation, auditing, credential generation, policy validation, or persistence logic in the dashboard.
- A generated enrollment credential may be returned only in the successful enrollment response. It must never be included in a URL, query parameter, data attribute, browser storage, history state, logs, errors, audit values, or a later read response. Clear the DOM and JavaScript reference when its dialog closes.
- All dynamic page values, including dialogs, use DOM creation, `textContent`, and safe properties/attributes. Do not use `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, inline handlers, `eval`, remote scripts, browser credential storage, or a UI framework.
- Browser code presents canonical server values only. It may format timestamps, units, and status labels, but must not infer availability, GPU health, incident state, telemetry values, or expected-inventory compliance.
- Preserve existing bounded polling, keyset pagination, drawer request abort/generation safeguards, history request bounds, text summaries, and native-SVG chart rendering. Mutation success refreshes canonical read data; it does not manufacture local device/project rows or chart points.
- Do not commit, push, contact an external provider, touch retained MySQL data/ACLs, reset/reinitialize MySQL, or perform production operations.

## Review Focus

- A cross-origin or unauthenticated mutation must not reach `IdentityService`; Task 2 owns route-level negative tests and the same-origin boundary.
- An enrollment credential must be transient and must not leak through subsequent reads, markup, browser storage, logs, or a URL; Tasks 2 and 4 own API and static UI checks.
- A duplicate click must not create duplicate projects/devices or issue duplicate move/enable requests; Task 4 owns explicit in-flight submission state and tests.
- Project creation launched from enrollment must refresh canonical projects and select the newly created project without creating a browser-only project; Task 4 owns this workflow.
- A stale or failed mutation/read refresh must not overwrite canonical dashboard/detail state or falsely report success; Task 4 owns sequencing, retained data, and error-state behavior.
- Visual polish must remain a single responsive operational experience rather than fake sections/pages, and must retain keyboard/focus/reduced-motion behavior; Task 3 owns shell/static tests and manual validation instructions.
- The pre-existing Stage 07.4 scope guard that rejected every `JSON.stringify` call must be narrowed: structured JSON mutation bodies now require it, while raw diagnostic/detail JSON rendering remains prohibited. Task 4 owns that test correction.

## Task 1: Establish a reusable mutation boundary and canonical management adapter

**Files:**
- Modify: `server/app/api/auth.py`
- Create: `server/app/dashboard/management.py`
- Create: `server/app/schemas/dashboard_management.py`
- Modify: `server/app/main.py`
- Modify: `server/tests/test_dashboard_api.py`
- Modify: `server/tests/test_config.py`

**Interfaces:**
- Expose `same_origin(request: Request) -> bool` from `app.api.auth` by promoting the existing logout-only `_same_origin` helper without changing its comparison rules. Logout must use the promoted helper, preserving current behavior.
- Define strict bounded request models: `ProjectCreateRequest`, `DeviceEnrollRequest`, `DeviceProjectUpdateRequest`, and `DeviceMonitoringUpdateRequest`.
- Define `DashboardManagementService(database: Database, *, actor: str)` as the sole dashboard mutation adapter. Its `create_project`, `enroll_device`, `move_device`, and `set_device_enabled` methods delegate to the named `IdentityService` methods and return display-safe dictionaries/dataclasses. `enroll_device` carries `GeneratedCredential` only to the route that serializes the one-time token.
- Establish `app.state.dashboard_management_service_factory`, accepting `(database, actor)` and defaulting to `DashboardManagementService`, for route tests to substitute a no-database fake.
- Extend the existing API cache middleware so every `/api/v1` response, including mutation success, validation, authorization, and origin failures, has `Cache-Control: no-store` while retaining existing GET behavior.

- [x] **Step 1: Write failing boundary and adapter tests**

Add focused tests that prove:

```python
def test_same_origin_retains_logout_origin_and_referer_rules():
    assert same_origin(request_with_matching_origin()) is True
    assert same_origin(request_with_foreign_origin()) is False


def test_dashboard_management_enroll_uses_the_canonical_identity_service(monkeypatch):
    # Substitute IdentityService and assert its actor, project UUID, name and GPUPolicy.
    # The result must expose a display-safe device projection and retain the generated
    # credential as a secret-bearing result, not as a logged/stringified service value.
    ...


def test_dashboard_management_request_models_reject_unbounded_or_invalid_input():
    assert_invalid(ProjectCreateRequest, {"name": " "})
    assert_invalid(DeviceEnrollRequest, {"name": "device", "project_id": "bad"})
    assert_invalid(DeviceMonitoringUpdateRequest, {"enabled": "yes"})
```

Use the repository’s current test client/model style and keep input bounds aligned with canonical project/device/GPU policy limits rather than inventing dashboard-only meanings.

- [x] **Step 2: Run the focused tests to verify RED**

Run from `server`:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_api.py tests/test_config.py -q
```

Expected: failures because the reusable same-origin helper, request schemas, management adapter, and factory do not yet exist.

- [x] **Step 3: Implement the bounded adapter without duplicating identity behavior**

1. Rename/promote `_same_origin` to `same_origin` in `app.api.auth`, update the logout route to call it, and retain the existing origin/referer/public-base-url behavior byte-for-byte where possible.
2. Add request schemas in `app.schemas.dashboard_management`:
   - project name: stripped, non-empty, bounded to the canonical `create_project` limit;
   - device name and project UUID: stripped/bounded and canonical UUID validated;
   - enrollment GPU controls: explicit strict boolean `gpu_monitoring_enabled`, bounded non-negative `expected_gpu_min_count`, and no user-controlled UUID inventory;
   - move project UUID and strict enable boolean.
3. Add `DashboardManagementService` that instantiates `IdentityService(database, actor=actor)` and delegates exactly once per method:
   - `create_project(name)` calls `create_project(name=name)`;
   - `enroll_device(...)` constructs the existing `GPUPolicy` from only monitoring-enabled and expected-count controls, then calls `enroll(project_uuid=..., name=..., policy=...)`;
   - `move_device(device_id, project_id)` calls `move`;
   - `set_device_enabled(device_id, enabled)` calls `set_enabled`.
4. Project/device result helpers produce primitive display-safe values only. They never return ORM objects, hashes, audit objects, session data, notification destinations, or token digests. Only the enrollment-result helper makes the existing `SecretStr` credential available for immediate successful-response serialization.
5. Set the service factory in `create_app`; use a type alias/protocol if needed to keep strict mypy precise.
6. Update the API cache middleware to cover the entire `/api/v1` namespace, not only GET requests. This is a security-header extension, not a monitoring semantic change.

- [x] **Step 4: Run focused boundary/adapter regressions to verify GREEN**

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_api.py tests/test_config.py -q
..\.venv\Scripts\ruff.exe check --no-cache app tests
..\.venv\Scripts\mypy.exe app --strict --cache-dir D:\skybeat\.stage07-6-task1-mypy-cache
```

Expected: current logout and development-bypass behavior remain unchanged, new bounded schemas/adapter are covered, and all touched Python code type-checks.

## Task 2: Add authenticated, same-origin dashboard management routes

**Files:**
- Modify: `server/app/api/dashboard.py`
- Modify: `server/tests/test_dashboard_api.py`
- Modify: `docs/API_SPEC.md`

**Interfaces:**
- `POST /api/v1/projects` accepts `ProjectCreateRequest` and returns `{"project": {"project_id", "name"}}`.
- `POST /api/v1/devices` accepts `DeviceEnrollRequest` and returns `{"device": {...}, "credential": "sb1..."}` only for that successful enrollment response.
- `PATCH /api/v1/devices/{device_uuid}/project` accepts `DeviceProjectUpdateRequest` and returns a display-safe moved-device projection.
- `PATCH /api/v1/devices/{device_uuid}/monitoring` accepts `DeviceMonitoringUpdateRequest` and returns a display-safe monitoring projection.
- Every route uses `DashboardUserDependency`, checks `same_origin(request)` before the service factory is called, performs synchronous service work through `asyncio.to_thread`, has no-store responses, and maps expected identity errors to safe 4xx responses.

- [x] **Step 1: Write failing route/security tests**

Use a fake management factory installed on the app state and assert all of the following:

```python
def test_project_creation_requires_the_existing_dashboard_user_and_no_store():
    response = client.post("/api/v1/projects", json={"name": "GPU Lab"})
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_cross_origin_device_enrollment_is_rejected_before_service_execution():
    response = authorized_client.post(
        "/api/v1/devices",
        headers={"Origin": "https://other.example"},
        json=valid_enrollment_body(),
    )
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert fake_management.calls == []


def test_authorized_management_routes_forward_a_dashboard_actor_and_safe_values_only():
    # Cover project creation, enrollment, project movement, and monitoring toggle.
    # Assert factory actor == authenticated email and no route returns an ORM-like object.
    ...


def test_enrollment_credential_is_one_time_response_data_only():
    response = authorized_client.post("/api/v1/devices", json=valid_enrollment_body())
    assert response.json()["credential"].startswith("sb1.")
    assert "credential" not in authorized_client.get("/api/v1/devices").text
    assert response.headers["cache-control"] == "no-store"


def test_invalid_mutation_payloads_and_canonical_identity_errors_are_safe_no_store_4xx():
    ...
```

Also add a test proving a development-bypass request obtains the same dashboard identity through these mutation routes; it must not introduce a special bypass-only route or bypass the origin check.

- [x] **Step 2: Run route tests to verify RED**

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_api.py -q
```

Expected: failures because no dashboard management mutation routes exist.

- [x] **Step 3: Implement the routes and document their safe contract**

1. Add the four routes to the existing dashboard API router; do not create a duplicate dashboard router or unauthenticated endpoint.
2. Use the existing canonical UUID validation convention for device path identifiers. Check `same_origin` before creating/using `DashboardManagementService`.
3. Catch `NotFoundError` and `ConflictError` before their broader identity error base class, returning existing safe 404/409 dashboard-style responses. Convert other expected validation/identity failures to 422 without echoing names, token material, database details, or exceptions. Let unexpected exceptions continue to the existing safe server error handler.
4. Serialize the credential’s secret value in exactly the successful enrollment JSON response. Do not place it in a response header, log message, exception, audit data, or reusable projection helper.
5. Add concise `docs/API_SPEC.md` contracts for each route: authentication, same-origin requirement, no-store, input bounds, response projection, and the enrollment credential’s one-time/transient nature. State that routes do not alter monitoring lifecycle semantics.

- [x] **Step 4: Run focused management/API regression tests to verify GREEN**

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_api.py tests/test_dashboard_read.py tests/test_dashboard_stage07_read.py -q
```

Expected: authorized reads remain compatible, mutation routes are bounded/authenticated/same-origin/no-store, and the existing development-bypass identity follows the same dependency boundary.

## Task 3: Build the premium single-page operational shell and responsive visual system

**Files:**
- Modify: `server/app/templates/dashboard.html`
- Modify: `server/app/static/dashboard.css`
- Modify: `server/app/static/dashboard.js`
- Modify: `server/tests/test_dashboard_page.py`

**Interfaces:**
- The page exposes one semantic application shell with `app-sidebar`, `dashboard-workspace`, overview, projects, and device inventory anchors; it must not add fake pages or navigation routes.
- The header retains authenticated identity/logout, adds a live-data indicator and exact last-successful-refresh time, and keeps semantic text available without color.
- Existing overview, project, table, drawer, GPU, and history identifiers required by the current script remain available or are changed together with their safe JavaScript references.

- [x] **Step 1: Write failing page/static design-safety tests**

Add tests that assert the rendered page/script/style provide:

```python
def test_dashboard_page_has_one_semantic_sidebar_shell_and_operational_sections():
    response = authenticated_dashboard_response()
    assert 'id="app-sidebar"' in response.text
    assert 'href="#overview-heading"' in response.text
    assert 'href="#devices-heading"' in response.text
    assert 'id="dashboard-workspace"' in response.text
    assert 'id="add-device"' in response.text
    assert 'id="new-project"' in response.text


def test_dashboard_visual_system_preserves_accessibility_and_responsive_behavior():
    stylesheet = dashboard_stylesheet()
    assert "prefers-reduced-motion" in stylesheet
    assert "@media" in stylesheet
    assert ":focus-visible" in stylesheet
    assert "position: sticky" in stylesheet


def test_dashboard_display_helpers_keep_canonical_states_and_exact_time_accessibility():
    script = dashboard_script()
    assert "formatRelativeTime" in script
    assert "title" in script
    assert "AWAITING_FIRST_HEARTBEAT" in script
    assert "computeAvailability" not in script
    assert "deriveGpu" not in script
```

Keep source checks focused on security and semantic affordances rather than pixel-perfect implementation details.

- [x] **Step 2: Run page/static tests to verify RED**

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py -q
```

Expected: failures because the Stage 07.5 layout does not yet expose the Stage 07.6 shell/action controls and visual tokens.

- [x] **Step 3: Implement the visual system without changing data semantics**

1. Restructure the template into one app shell: compact branded sidebar with in-page anchors for Overview, Devices, and Projects; compact header with authenticated identity/logout; and a main workspace containing existing operational sections. Keep the page title and landmarks meaningful without JavaScript.
2. Add clear, responsive CSS custom properties for background/surfaces, text/muted text, canonical status colors, spacing, radius, shadows, and typography. Use system fonts only.
3. Restyle summary cards, project cards, controls, table, status pills, detail drawer, GPU blocks, and Stage 07.5 native charts. Retain canonical values and non-color labels/icons. Keep the Awaiting First Heartbeat count visibly separate from online/suspect/offline cards.
4. Add `formatRelativeTime`/exact timestamp presentation to existing safe renderers: human-readable text is visible, while a complete UTC/local exact value is available in `title` and/or accessible text. Preserve null as `—`; do not convert zero to missing or manufacture data.
5. Make the device table dense but usable, sticky only where responsive layout permits it, with horizontal containment on narrow screens and no forced word-breaking of UUIDs/hostnames/models. Preserve focus visibility, keyboard order, textual loading/error/stale states, and `prefers-reduced-motion` behavior.
6. Keep the existing drawer non-modal for diagnostics. Visual grouping may improve identity/freshness/system/storage/GPU/policy/incidents/history but must not add another data source or alter existing request behavior.

- [x] **Step 4: Run visual-shell and existing dashboard regression tests to verify GREEN**

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py tests/test_dashboard_api.py tests/test_dashboard_stage07_read.py tests/test_dashboard_read.py -q
```

Expected: the one-page dashboard remains safe, accessible, bounded, and compatible with Stage 07.2–07.5 APIs.

## Task 4: Implement safe project creation, device enrollment, and device controls in the dashboard

**Files:**
- Modify: `server/app/templates/dashboard.html`
- Modify: `server/app/static/dashboard.js`
- Modify: `server/app/static/dashboard.css`
- Modify: `server/tests/test_dashboard_page.py`

**Interfaces:**
- Project dialog: `project-dialog`, `project-form`, `project-name`, `project-status`, and an explicit close control.
- Enrollment dialog: `device-enroll-dialog`, `device-enroll-form`, `enroll-name`, `enroll-project`, `enroll-gpu-enabled`, `enroll-gpu-count`, `enrollment-credential`, `copy-enrollment-credential`, and explicit dismiss controls.
- Device actions operate only on the currently selected canonical `selectedDeviceId`: `detail-change-project` and `detail-toggle-monitoring`, each with an accessible confirmation dialog and status area.
- JavaScript exposes focused helpers `openProjectDialog`, `submitProject`, `openEnrollmentDialog`, `submitEnrollment`, `clearEnrollmentCredential`, `copyEnrollmentCredential`, `requestDashboardMutation`, `openMoveDialog`, and `openMonitoringConfirmation`.

- [x] **Step 1: Write failing static workflow/security tests**

Add static tests that prove the implementation contains the required safe lifecycle rather than testing browser internals unavailable in this repository:

```python
def test_dashboard_management_uses_same_origin_json_mutations_and_no_browser_storage():
    script = dashboard_script()
    assert 'fetch("/api/v1/projects"' in script
    assert 'fetch("/api/v1/devices"' in script
    assert 'method: "POST"' in script
    assert 'method: "PATCH"' in script
    assert 'credentials: "same-origin"' in script
    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert "history.pushState" not in script


def test_dashboard_enrollment_credential_is_explicitly_transient_and_copy_only_on_action():
    script = dashboard_script()
    assert "clearEnrollmentCredential" in script
    assert "navigator.clipboard.writeText" in script
    assert "enrollmentCredential = null" in script
    assert "dialog.close" in script
    assert "data-credential" not in dashboard_template()


def test_dashboard_management_has_duplicate_submission_and_confirmation_guards():
    script = dashboard_script()
    assert "projectSubmissionInFlight" in script
    assert "enrollmentSubmissionInFlight" in script
    assert "moveSubmissionInFlight" in script
    assert "monitoringSubmissionInFlight" in script
    assert "detail-change-project" in dashboard_template()
    assert "detail-toggle-monitoring" in dashboard_template()


def test_dashboard_never_uses_unsafe_html_and_only_stringifies_structured_mutation_bodies():
    script = dashboard_script()
    for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert unsafe not in script
    assert "JSON.stringify(payload)" in script
    assert "renderRawJson" not in script
```

Update the former Stage 07.4 broad `JSON.stringify` prohibition to this precise guard: it protects against raw diagnostic rendering while allowing the new structured request body required by the authenticated mutation API.

- [x] **Step 2: Run workflow tests to verify RED**

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py -q
```

Expected: failures because no project/enrollment/control dialogs and mutation lifecycle exist.

- [x] **Step 3: Implement explicit, transient, canonical workflows**

1. Add native accessible dialogs and forms to the template. All initial dialog/status/credential fields are empty/hidden, have labelled controls, and support Escape/cancel/explicit close. Do not put device IDs, project IDs, or credentials in unsafe attributes; ordinary selected option values and button references may carry canonical public IDs only.
2. Maintain bounded in-memory dashboard state for the most recently read project list and the four independent submission flags. Disable the relevant submit/action controls during a request and restore them in `finally`; never disable unrelated dashboard reads or actions unnecessarily.
3. Implement `requestDashboardMutation(path, method, payload)` with a same-origin relative URL, `credentials: "same-origin"`, JSON content type, `JSON.stringify(payload)` only for the explicit structured request body, safe response parsing, and user-visible generic errors. It must not put any input in a URL or console log.
4. Implement project creation by POSTing only the canonical required project name. On success, refresh canonical overview/project/device data, repopulate project selects from the refreshed projection, announce success, and—when launched from enrollment—select the newly returned canonical project ID. Do not create a local substitute project row.
5. Implement enrollment by POSTing name, selected project UUID, and existing GPU monitoring/minimum-count controls. Validate basic form completeness before the request, but leave authoritative validation to the server. On success, show the one-time credential in a dedicated text-only element and permit `navigator.clipboard.writeText` only from the explicit Copy click. `clearEnrollmentCredential` runs on every dismiss/cancel/close and on reopening, blanks the element, disables Copy, and clears the JavaScript variable. After the operator acknowledges/dismisses the credential, refresh canonical data and optionally open the new device’s canonical detail.
6. Implement selected-device project move and enable/disable controls as confirmation dialogs. Never infer current state: render the target/current project and monitoring text from canonical detail/read data, POST/PATCH only after explicit confirmation, refresh canonical data/detail after success, and retain prior visual data with a clear error on failure.
7. Preserve the existing dashboard’s non-overlapping visible/hidden polling. Mutation-driven refreshes must use its existing in-flight guard and must not create a second timer. Keep all stage 07.4/07.5 AbortController/generation protections; close/deselect operations must not permit a late detail/history response to overwrite a new selection.

- [x] **Step 4: Run focused UI/API regression tests to verify GREEN**

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py tests/test_dashboard_api.py tests/test_dashboard_stage07_read.py tests/test_dashboard_read.py -q
```

Expected: management UI has guarded same-origin workflows, safe transient credential handling, and all existing dashboard read/detail/history behavior remains compatible.

## Task 5: Add integration-level management regressions and stage-specific manual browser acceptance instructions

**Files:**
- Modify: `server/tests/test_dashboard_api.py`
- Modify: `server/tests/test_dashboard_page.py`
- Modify: `docs/DEPLOYMENT_RUNBOOK.md`
- Modify: `docs/API_SPEC.md`

**Interfaces:**
- API tests exercise the management factory through the same `dashboard_user` dependency in both opaque-session and explicitly enabled development-bypass configurations.
- The runbook has a clearly labelled local-only browser test procedure using `SKYBEAT_ENV=development` and `SKYBEAT_DEV_AUTH_BYPASS=true`; it never tells an operator to enable the bypass in production.

- [x] **Step 1: Write failing acceptance-regression tests and safety text assertions**

Add checks that cover:

```python
def test_management_routes_do_not_change_existing_read_projections_or_monitoring_endpoints():
    # Existing GET API contracts retain their paths, no-store headers, and display-safe fields.
    ...


def test_local_bypass_can_use_management_routes_but_production_cannot_enable_it():
    # Reuse configuration/dependency fixtures; do not mock a separate auth model.
    ...


def test_runbook_labels_the_bypass_local_only_and_does_not_display_credentials():
    text = deployment_runbook()
    assert "SKYBEAT_DEV_AUTH_BYPASS=true" in text
    assert "development" in text.lower()
    assert "production" in text.lower()
    assert "never" in text.lower()
```

- [x] **Step 2: Run focused acceptance checks to verify RED**

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_api.py tests/test_dashboard_page.py tests/test_config.py -q
```

Expected: at least the runbook assertion fails before its Stage 07.6 local-browser procedure is added.

- [x] **Step 3: Document the safe manual browser procedure**

Add a concise local-development-only section to `docs/DEPLOYMENT_RUNBOOK.md`:

1. Set `SKYBEAT_ENV=development` and `SKYBEAT_DEV_AUTH_BYPASS=true` only in a protected ignored local environment file; restart the local API and confirm the prominent startup warning.
2. Navigate to the existing dashboard origin and verify sidebar/header/live status, compact summaries, projects, filters, table, detail drawer, GPU blocks, range switching, responsive widths (1440, 1024, 768, and narrow mobile), keyboard focus, Escape/close paths, and reduced-motion behavior.
3. Create a project, verify canonical refresh, enroll a device, copy the credential once without recording it, close the dialog, and confirm it is no longer displayed. Move a selected device and toggle monitoring only after explicit confirmation, then verify canonical refreshes.
4. Disable the bypass by setting `SKYBEAT_DEV_AUTH_BYPASS=false` or removing it and restarting. State explicitly that production configuration rejects the flag and Google OIDC remains required when it is off.

Do not include a real credential, device token, database URL, or a procedure that changes retained MySQL ACLs/data.

- [x] **Step 4: Run focused acceptance regression tests to verify GREEN**

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_api.py tests/test_dashboard_page.py tests/test_config.py -q
```

Expected: safe bypass documentation, API boundary, static UI restrictions, and existing dashboard/read behavior all pass together.

## Task 6: Final Stage 07.6 executable verification and checkpoint

**Files:**
- Modify: `docs/IMPLEMENTATION_STATUS.md`
- Test: `server/tests/test_dashboard_api.py`
- Test: `server/tests/test_dashboard_page.py`

**Interfaces:**
- Produces a truthful Stage 07.6 checkpoint marked `IMPLEMENTED / AWAITING VISUAL ACCEPTANCE`, not `COMPLETE / ACCEPTED`.
- Retains overall Stage 07 `IN PROGRESS`, Stage 08 not started, all prior Stage 07.1–07.5 evidence, and current environment-specific MySQL/Bash/Linux limitations.

- [x] **Step 1: Inspect the final diff for scope and secret safety**

Run:

```text
git diff -- . ':!.env'
git diff --check
```

Confirm only the planned dashboard/API/config/documentation/test changes are present, no token-like fixture or real secret has been added, no migration exists, and no Stage 08/remote-administration behavior appears.

- [x] **Step 2: Run final verification**

Run from `server` unless stated otherwise:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py tests/test_dashboard_api.py tests/test_dashboard_stage07_read.py tests/test_dashboard_read.py -q
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q
..\.venv\Scripts\ruff.exe check --no-cache app tests migrations ..\scripts
..\.venv\Scripts\ruff.exe format --check --no-cache app tests migrations ..\scripts
..\.venv\Scripts\mypy.exe app --strict --cache-dir D:\skybeat\.stage07-6-mypy-cache
..\.venv\Scripts\python.exe -m alembic heads
..\.venv\Scripts\python.exe -m alembic history
..\.venv\Scripts\python.exe ..\scripts\validate_deployment.py
git -C .. diff --check
```

Do not rerun the agent suite unless a Stage 07.6 change touches agent code, the heartbeat/shared agent contract, or deployment artifacts. It should not: this stage is dashboard server/template/static/test/documentation work only. Do not start MySQL or change retained data/ACLs merely to remove environment skips.

- [x] **Step 3: Update the implementation checkpoint only after the commands pass**

Update `docs/IMPLEMENTATION_STATUS.md` to record:

- Stage 07.6 implemented visual polish plus canonical Create + Select project workflow, device enrollment/one-time credential display, project reassignment, and monitoring enable/disable confirmations;
- no migration and unchanged availability/GPU/heartbeat/history/incident semantics;
- exact focused/full server test counts, skips, Ruff, format, strict mypy, Alembic history, deployment validation, and diff result;
- that the agent suite was not rerun only because no relevant agent/shared/deployment file changed;
- the local-only dev bypass configuration prerequisite and manual browser acceptance procedure;
- retained unavailable real-MySQL, browser/manual visual, Linux/Docker/Caddy/systemd/deployment evidence as environment-pending, without claiming it was performed;
- `Stage 07.6 — IMPLEMENTED / AWAITING VISUAL ACCEPTANCE`, overall Stage 07 still `IN PROGRESS`, and Stage 08 explicitly not started.

## Plan Self-Review

- Scope coverage: Tasks 1–2 add only the approved authenticated canonical mutation boundary; Tasks 3–4 deliver the visual/dashboard workflows; Task 5 documents local visual acceptance; Task 6 verifies and records a non-final checkpoint.
- Credential safety: only the enrollment success response contains the generated token; service/routing, DOM lifecycle, static tests, and runbook rules each own a different leak prevention boundary.
- Authorization consistency: every mutation uses the existing dashboard identity and promoted existing same-origin comparison. The development bypass works only as an existing resolved identity and production rejection remains configuration-owned.
- Monitoring compatibility: UI formatting and refresh are presentation-only. No task changes canonical read calculations, alert lifecycle, history limits, or database schema.
- Failure ownership: cross-origin/auth, duplicate submissions, project-selection refresh, late responses, credential cleanup, restricted raw JSON behavior, responsive accessibility, and environment-dependent verification all have explicit task/test ownership.
- Execution constraint: implement this plan natively in the shared workspace; do not delegate or create a separate worktree, do not commit, and do not start Stage 08.
