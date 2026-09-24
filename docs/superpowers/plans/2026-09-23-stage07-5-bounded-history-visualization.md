# Stage 07.5 Bounded History Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded, accessible native-SVG telemetry history to the existing selected-device drawer without changing the authoritative history API or any monitoring lifecycle.

**Architecture:** The existing authorized Stage 07.2 history projection remains the sole source. The Stage 07.4 drawer owns a selected history range, one abortable/generation-protected request, and bounded DOM output. Native SVG supplies supplemental visual charts while compact text summaries are the accessible alternative.

**Tech Stack:** FastAPI read projection (unchanged), Jinja2, vanilla JavaScript DOM/SVG APIs, CSS, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-23-stage07-dashboard-runbook-design.md`; `C:\Users\mahar\.codex\attachments\58b2103b-e966-4f80-9d0a-e50eb626c41e\Pasted text.txt`

## Global Constraints

- Implement Stage 07.5 only. Do not start Stage 08, change heartbeat ingestion, availability, GPU-health semantics, incidents, identity, authorization, sessions, CSP, or deployment.
- Use only `GET /api/v1/devices/{device_uuid}/history?range=1h|6h|24h|7d`; do not change its endpoint, response, raw-read cap (5,000 retained from at most 5,001 reads), returned-point cap (240), 64-GPU-series cap, ordering, or truncation semantics.
- History requests are only for the selected device and selected range. Default range is `1h`; range controls are exactly `1h`, `6h`, `24h`, and `7d`.
- Native SVG must be created through `document.createElementNS`; use safe attributes and `textContent`. Do not use `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, canvas, external scripts, or chart/framework dependencies.
- Treat null/missing/non-finite values as absent and never as zero. Preserve numeric zero. Do not merge UUID and index GPU identities, fabricate samples, compute health, or browser-side downsample.
- Integrate with the existing visible 15-second/hidden 60-second dashboard cycle. Do not create another timer, prefetch devices/ranges, request raw heartbeat data, or retain unbounded points.
- No schema migration, dependency, commit, push, production operation, or retained-MySQL ACL/data action.

## Review Focus

- Device-A or older-range history must not overwrite the currently selected device/range; Task 2 owns generation and abort guards.
- A null metric must break/omit a line while numeric zero remains a valid measurement; Task 2 owns the renderer/source guards.
- UUID and index GPU identities must stay separate even when indices match; Task 2 owns distinct-series rendering and legend/summary guards.
- History errors must not remove canonical detail or incidents; Task 2 owns independent state/retry behavior.
- Server `truncated` and `series_truncated` must be represented honestly without larger/raw follow-up reads; Tasks 1 and 2 own the notice and request-scope guards.

---

### Task 1: Accessible bounded history shell

**Files:**
- Modify: `server/app/templates/dashboard.html`
- Modify: `server/tests/test_dashboard_page.py`

**Interfaces:**
- Produces drawer elements `history-range-controls`, `history-status`, `history-retry`, `history-truncation`, and `history-content`.
- Consumes the existing Stage 07.4 drawer and the fixed server range vocabulary.

- [x] **Step 1: Write failing history-shell tests**

```python
def test_dashboard_detail_contains_bounded_history_controls_and_accessible_output():
    response = authenticated_dashboard_response()
    for identifier in (
        "history-range-controls",
        "history-status",
        "history-retry",
        "history-truncation",
        "history-content",
    ):
        assert f'id="{identifier}"' in response.text
    for range_name in ("1h", "6h", "24h", "7d"):
        assert f'data-history-range="{range_name}"' in response.text
```

- [x] **Step 2: Run the focused page test to verify RED**

Run from `server`:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py -q
```

Expected: FAIL because the Stage 07.4 drawer has no telemetry-history shell.

- [x] **Step 3: Add the non-modal History/Telemetry drawer section**

Add a labelled drawer section after recent incidents. Include a keyboard-native button group with exact range values and `aria-pressed` state, an `aria-live="polite"` status, a hidden Retry button, a visible-but-subtle bounded-history notice container, and a content container. Keep all headings and controls in the existing drawer; do not add a route, raw telemetry display, or SVG markup in the template.

- [x] **Step 4: Run the focused page test to verify GREEN**

Run the Step 2 command. Expected: PASS, retaining Stage 07.3/07.4 page, escaping, and authorization coverage.

### Task 2: Native SVG rendering and controlled history lifecycle

**Files:**
- Modify: `server/app/static/dashboard.js`
- Modify: `server/app/static/dashboard.css`
- Modify: `server/tests/test_dashboard_page.py`

**Interfaces:**
- Consumes the unchanged history projection: `{range, from, to, truncated, raw_sample_count, cpu_utilization, memory_utilization, gpu_series, series_truncated}`.
- Produces `requestDeviceHistory(deviceId, rangeName, signal)`, `loadHistory(deviceId, rangeName)`, `refreshOpenHistory()`, range-selection handlers, and safe chart/summary renderers.

- [x] **Step 1: Write failing static lifecycle/rendering contract tests**

```python
def test_dashboard_history_uses_only_the_canonical_bounded_endpoint_and_native_svg():
    script = dashboard_script()
    assert "const HISTORY_RANGES = [\"1h\", \"6h\", \"24h\", \"7d\"]" in script
    assert 'fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}/history?${query}`' in script
    assert 'query.set("range", rangeName)' in script
    assert "document.createElementNS" in script
    assert "AbortController" in script
    assert "historyGeneration" in script
    assert "heartbeat_samples" not in script
    assert "Chart" not in script
    assert "createElement(\"canvas\")" not in script


def test_dashboard_history_source_guards_missing_zero_gpu_and_truncation_behavior():
    script = dashboard_script()
    assert "Number.isFinite(value)" in script
    assert "value === 0" in script
    assert "series.identity?.kind" in script
    assert "History was bounded by the server" in script
    assert "History could not be loaded." in script
```

- [x] **Step 2: Run the focused page test to verify RED**

Run the Task 1 Step 2 command. Expected: FAIL because history request state, native SVG, summaries, and range handling do not exist.

- [x] **Step 3: Implement bounded history loading and safe rendering**

Add a `HISTORY_RANGES` constant, `selectedHistoryRange = "1h"`, `historyGeneration`, `historyAbortController`, and one retained bounded successful history projection. `requestDeviceHistory` must build a `URLSearchParams` query from the fixed allowed range and use same-origin credentials. `loadHistory` increments generation, aborts the preceding request, and applies a result only if device ID, range, generation, and drawer selection still match.

Render four chart cards: CPU utilization, memory utilization, GPU utilization, and GPU temperature. Build every SVG node with `document.createElementNS`; calculate only presentation geometry from valid chronological points. A null/missing/non-finite value ends a line segment; zero is retained. CPU, memory, and GPU utilization use percentage semantics; temperature uses degrees Celsius. Render every GPU series separately using the server identity (`UUID` preferred, index fallback), with a restrained distinct line color, legend, and per-series bounded summary (identity, usable-observation count, latest/min/max). Never generate data values, derive GPU health, or merge identities.

Show loading, empty, initial error plus Retry, retained-stale history on refresh error, `truncated`/`series_truncated` notices, and concise text summaries. Detail and incidents remain present on history failure. Call history loading only after selected canonical detail succeeds; call `refreshOpenHistory()` once after a successful selected-detail refresh in the existing dashboard cycle. On device close/switch, invalidate and abort history. Range changes load only the selected device and newest selected range; no new timers or concurrent range fetches.

- [x] **Step 4: Run focused page/API/read regression tests to verify GREEN**

Run from `server`:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py tests/test_dashboard_api.py tests/test_dashboard_stage07_read.py tests/test_dashboard_read.py -q
```

Expected: PASS. Existing Stage 07.2 history bounds and Stage 07.3/07.4 dashboard behavior remain compatible.

### Task 3: Responsive chart presentation and acceptance checkpoint

**Files:**
- Modify: `server/app/static/dashboard.css`
- Modify: `docs/IMPLEMENTATION_STATUS.md`
- Test: `server/tests/test_dashboard_page.py`

**Interfaces:**
- Consumes the Task 2 history cards/SVG/text summaries.
- Produces responsive, drawer-contained history presentation and a Stage 07.5 acceptance checkpoint while keeping Stage 07 in progress.

- [x] **Step 1: Write a failing responsive/history-scope test**

```python
def test_dashboard_history_is_responsive_and_excludes_unbounded_or_external_renderers():
    styles = dashboard_styles()
    script = dashboard_script()
    assert ".history-chart" in styles
    assert "max-width: 100%;" in styles
    assert "window.setInterval" not in script
    assert "/heartbeats" not in script
    for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert unsafe not in script
```

- [x] **Step 2: Run the page test to verify RED**

Run the Task 1 Step 2 command. Expected: FAIL because responsive history-chart styling and the Stage 07.5 source guards are absent.

- [x] **Step 3: Add responsive restrained chart CSS**

Style chart cards, compact legends, summaries, range buttons, notices, and SVGs within the existing drawer. Use responsive `viewBox` sizing and `max-width: 100%`; stack cards on narrow screens. Preserve visible keyboard focus, text labels, and non-color-only state indicators. Do not enlarge the drawer beyond its existing responsive boundary or add animation, gradients, external assets, or framework styles.

- [x] **Step 4: Update status only after evidence**

After every executable check passes, update `docs/IMPLEMENTATION_STATUS.md` to mark Stage 07.5 COMPLETE / ACCEPTED while retaining Stage 07 IN PROGRESS. Record the exact fresh verification, unchanged Stage 07.2 bounds/no migration, skipped agent suite rationale, MySQL/browser pending evidence, and that Stage 08 is not started.

- [x] **Step 5: Run final verification**

Run from `server`:

```text
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_page.py tests/test_dashboard_api.py tests/test_dashboard_stage07_read.py tests/test_dashboard_read.py -q
..\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q
..\.venv\Scripts\ruff.exe check --no-cache app tests migrations ..\scripts
..\.venv\Scripts\ruff.exe format --check --no-cache app tests migrations ..\scripts
..\.venv\Scripts\mypy.exe app --strict --cache-dir D:\skybeat\.stage07-5-mypy-cache
..\.venv\Scripts\python.exe -m alembic heads
..\.venv\Scripts\python.exe -m alembic history
..\.venv\Scripts\python.exe ..\scripts\validate_deployment.py
git -C .. diff --check
```

Do not rerun the agent suite: Stage 07.5 changes only dashboard template/static/test/docs files and does not alter agent code, heartbeat schemas, shared agent contracts, or deployment artifacts. Retained MySQL and browser execution remain explicitly environment-pending.

## Plan Self-Review

- Spec coverage: Task 1 adds the range/accessibility shell; Task 2 owns canonical bounded requests, four history views, native SVG, null/zero behavior, GPU identity, summaries, errors, truncation, races, and polling; Task 3 owns responsive styling, scope guards, status, and all acceptance checks.
- Placeholder scan: no raw telemetry endpoint, chart library, migration, client resampling, device-wide prefetch, external script, or Stage 08 behavior is proposed.
- Type consistency: only server-established JSON fields are consumed; `rangeName` remains one of the exact four client constants; `selectedDeviceId`, selected range, and `historyGeneration` are the request-application boundary.
- Review focus: device/range races, missing versus zero, sparse GPU identities, independent error retention, and truncation honesty are each assigned to tests and implementation in Task 2.

## Execution Handoff

This plan is intended for native implementation in the existing working tree. It records the user’s no-commit/no-push restriction and the active collaboration restriction against spawning subagents.
