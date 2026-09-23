# Stage 07.2 Operational Dashboard Read API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded, authorization-protected operational dashboard read projections without changing canonical monitoring semantics or adding a schema migration.

**Architecture:** Keep all database reads in `DashboardReadService` and all HTTP adaptation in `app.api.dashboard`. Reuse `device_view()` and `_state()` for availability, stale telemetry, and effective GPU state; query the existing device/latest, incident/event, and heartbeat-sample records only. Use versioned base64url keyset cursors with strict decoding and limit-plus-one fetching; the cursor is opaque API data, never an ORM object or SQL clause.

**Tech Stack:** FastAPI, SQLAlchemy 2, MySQL-compatible queries, Pydantic/FastAPI query validation, Python standard library base64/JSON, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-23-stage07-dashboard-runbook-design.md`

## Global Constraints

- Implement Stage 07.2 API/read-service work only; do not change the dashboard UI, static assets, templates, heartbeat ingestion/schema, availability/GPU/incident/notification lifecycle, or authentication/session behavior.
- Every new endpoint uses `DashboardUserDependency`, dispatches synchronous reads through `asyncio.to_thread`, returns `Cache-Control: no-store`, and returns display-safe dictionaries only.
- The existing authorization model has no project/device claims: each authorized `DashboardUser` has the same global project/device visibility. Do not invent a partial scope model; all new queries follow that established visibility.
- Reuse `_state` and `device_view`; GPU problem/effective filtering uses `NOT MONITORED` when GPU monitoring is disabled and otherwise the persisted `device.gpu_effective_state`.
- Preserve existing compatible device filters and their errors. List/incident limits default to 50, accept 1 through 100, and FastAPI rejects invalid integer limits with its standard 422 response.
- No Alembic migration, cache, new dependency, external call, database reset, ACL change, production operation, commit, or Stage 07.3 UI work.
- Use `HeartbeatSample` only through its existing `(device_id, received_at)` index. History reads at most `HISTORY_RAW_CAP + 1` newest samples; `HISTORY_RAW_CAP = 5_000` and `HISTORY_POINT_CAP = 240` are explicit constants.
- When raw history exceeds the cap, retain the most recent 5,000 samples, return them in chronological order after deterministic downsampling, and set `truncated: true`. Bound historical GPU series to the current canonical maximum of 64 and expose a separate `series_truncated` flag if distinct identities exceed that bound.

## Review Focus

- Malformed, oversized, mismatched-version, or type-confused cursors must be rejected as dashboard-query 422 responses, never interpreted as database pagination state. Task 1 owns these tests.
- `AWAITING_FIRST_HEARTBEAT`, GPU `NOT MONITORED`, and non-OK effective GPU state must use the same `device_view()` rules for overview, filtering, and list display. Task 2 owns these tests.
- Keyset page boundaries must neither duplicate nor skip equal project/device names; UUID is the stable final tie-breaker. Task 2 owns this test.
- Incident reads must never expose event/delivery/provider/recipient information even if those rows exist. Task 3 owns this test.
- History must retain null/missing metrics, prefer GPU UUID over index fallback, and bound both raw read and returned points under sparse/changing GPU inventory. Task 4 owns these tests.

---

### Task 1: Shared bounded cursor and history projection primitives

**Files:**
- Modify: `server/app/dashboard/read.py`
- Create: `server/tests/test_dashboard_stage07_read.py`

**Interfaces:**
- Produces `decode_device_cursor(value: str | None) -> DeviceCursor | None`, `encode_device_cursor(cursor: DeviceCursor) -> str`, `decode_incident_cursor(value: str | None) -> IncidentCursor | None`, and `downsample_history(samples: list[HeartbeatSample]) -> dict[str, object]` for later service methods.
- Consumes canonical `HeartbeatSample.payload` structures (`cpu.utilization_percent`, `memory.utilization_percent`, and `gpus[*].uuid/index/utilization_percent/temperature_celsius`).

- [ ] **Step 1: Write failing pure-function tests**

```python
def test_device_cursor_round_trips_but_rejects_malformed_and_oversized_input():
    cursor = DeviceCursor(project_name="A", device_name="Node", device_uuid=DEVICE_UUID)
    assert decode_device_cursor(encode_device_cursor(cursor)) == cursor
    for value in ("not-a-cursor", "A" * 513, encode_wrong_version_cursor()):
        with pytest.raises(ValueError, match="Cursor is invalid"):
            decode_device_cursor(value)


def test_downsample_history_prefers_gpu_uuid_and_preserves_missing_metrics():
    result = downsample_history(samples_with_uuid_and_index_fallback_and_nulls())
    assert result["cpu"][0]["value"] is None
    assert result["gpus"]["uuid:GPU-a"]["utilization"][0]["value"] == 41.0
    assert result["gpus"]["index:3"]["temperature"][0]["value"] is None
```

- [ ] **Step 2: Run the new pure-function tests to verify RED**

Run: `..\\.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_stage07_read.py -q`

Expected: FAIL because cursor codecs and history projection helpers do not exist.

- [ ] **Step 3: Implement strict opaque cursor codecs and deterministic history projection**

```python
DEVICE_CURSOR_VERSION = 1
CURSOR_MAX_LENGTH = 512
HISTORY_RAW_CAP = 5_000
HISTORY_POINT_CAP = 240
HISTORY_GPU_SERIES_CAP = 64

@dataclass(frozen=True)
class DeviceCursor:
    project_name: str
    device_name: str
    device_uuid: str


def _decode_cursor(value: str, kind: str) -> dict[str, object]:
    # Enforce maximum token length, urlsafe-base64 decoding, UTF-8 JSON object,
    # exact cursor version/kind/fields, safe string lengths, and canonical UUID.
    encoded = value.encode("ascii")
    padded = encoded + b"=" * (-len(encoded) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    if payload["v"] != 1 or payload["kind"] != kind:
        raise ValueError("Cursor is invalid.")
    return payload


def downsample_history(samples: list[HeartbeatSample]) -> dict[str, object]:
    # Samples arrive oldest-to-newest. For each retained ordinal bucket, choose
    # its final sample; emit timestamp/value records and preserve `None` values.
    step = max(1, math.ceil(len(samples) / HISTORY_POINT_CAP))
    selected = [samples[min((bucket + 1) * step, len(samples)) - 1]
                for bucket in range(math.ceil(len(samples) / step))]
    return _history_series(selected)
```

Use a pure bucket representative rule: for `n > HISTORY_POINT_CAP`, keep the final sample of each equal-width ordinal bucket, which preserves chronology and the most recent observation. Build a bounded identity map from UUID (`uuid:<uuid>`) or index (`index:<integer>`); UUID wins when present. Do not return sample payloads, raw telemetry objects, or arbitrary GPU keys.

- [ ] **Step 4: Run the pure-function tests to verify GREEN**

Run: `..\\.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_stage07_read.py -q`

Expected: PASS.

### Task 2: Overview and canonical device-list projections

**Files:**
- Modify: `server/app/dashboard/read.py`
- Modify: `server/app/api/dashboard.py`
- Modify: `server/tests/test_dashboard_stage07_read.py`
- Modify: `server/tests/test_dashboard_api.py`

**Interfaces:**
- Consumes Task 1 `DeviceCursor` codecs and existing `device_view()`/`_state()`.
- Produces `DashboardReadService.overview() -> dict[str, object]` and extends `list_devices` with `gpu_state: str | None` and `cursor: str | None`; exposes `GET /api/v1/dashboard/overview` and compatible `GET /api/v1/devices` parameters.

- [ ] **Step 1: Write failing overview/list API and service tests**

```python
def test_device_view_list_adds_safe_primary_ip_latest_receipt_and_gpu_count():
    view = device_view(device, project, latest, now)
    assert view["primary_ip"] == "192.0.2.10"
    assert view["latest_received_at"] == "2026-09-23T10:00:00.000000Z"
    assert view["gpu_count"] == 2


def test_list_devices_uses_uuid_keyset_tiebreaker_and_effective_gpu_filter(fake_database):
    first = service.list_devices(limit=1, gpu_state="DRIVER_ERROR")
    second = service.list_devices(limit=1, gpu_state="DRIVER_ERROR", cursor=first["next_cursor"])
    assert [item["device_id"] for item in first["items"] + second["items"]] == [UUID_A, UUID_B]


def test_overview_and_devices_require_dashboard_authorization_and_no_store(client):
    assert client.get("/api/v1/dashboard/overview").status_code == 401
    response = authorized_client.get("/api/v1/devices?gpu_state=INVALID")
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
```

- [ ] **Step 2: Run those tests to verify RED**

Run: `..\\.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_stage07_read.py tests/test_dashboard_api.py -q`

Expected: FAIL because overview, GPU filtering, validated opaque cursors, and added device display fields are absent.

- [ ] **Step 3: Implement overview and extend the device list without redefining state**

```python
def effective_gpu_state(device: Device) -> str:
    return "NOT MONITORED" if not device.gpu_monitoring_enabled else device.gpu_effective_state


def overview(self) -> dict[str, object]:
    # Use bounded aggregate/grouped SQL reads. Availability buckets match _state():
    # NULL last_seen => awaiting; other rows use availability_state.
    # GPU problem => effective state not in {OK, NOT MONITORED}.
    # Project distribution sorts (name, public_id), reads at most 101 rows,
    # returns at most 100 display-safe summaries and projects_truncated.
    return {
        "counts": counts,
        "projects": project_items,
        "projects_truncated": project_has_more,
        "server_time": _timestamp(now),
    }


def list_devices(
    self, *, gpu_state: str | None = None, cursor: str | None = None, **existing_filters: object
) -> dict[str, object]:
    # Validate canonical GPU state, decode cursor, retain all current filters,
    # apply (project name, device name, UUID) keyset predicate, fetch limit + 1,
    # and return encoded next_cursor only if an extra record exists.
    records = session.execute(statement.limit(limit + 1)).all()
    page = records[:limit]
    return {
        "items": [device_view(device, project, latest, now) for device, project, latest in page],
        "next_cursor": encode_device_cursor(_device_cursor(page[-1])) if len(records) > limit else None,
        "server_time": _timestamp(now),
        "worker_healthy": True,
    }
```

Extend `device_view()` with `primary_ip`, `latest_received_at`, and nullable `gpu_count`; source all three from `DeviceLatest`/the canonical payload. `gpu_count` is `None` when no latest telemetry exists and otherwise `len(gpus)` only when `gpus` is a canonical list. Keep existing `received_at` for compatibility. Add API query parameters `gpu_state` and `cursor`; convert only dashboard query `ValueError` to the established safe 422 response.

- [ ] **Step 4: Run the changed dashboard tests to verify GREEN**

Run: `..\\.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_stage07_read.py tests/test_dashboard_api.py tests/test_dashboard_page.py -q`

Expected: PASS, including existing page compatibility.

### Task 3: Bounded incident and device-history endpoints

**Files:**
- Modify: `server/app/dashboard/read.py`
- Modify: `server/app/api/dashboard.py`
- Modify: `server/tests/test_dashboard_stage07_read.py`
- Modify: `server/tests/test_dashboard_api.py`

**Interfaces:**
- Consumes Task 1 `IncidentCursor` and history projector plus existing `Incident`, `Device`, `Project`, `HeartbeatSample` records.
- Produces `list_incidents(limit: int, cursor: str | None) -> dict[str, object]`, `device_history(device_uuid: str, range_name: str) -> dict[str, object]`, `GET /api/v1/incidents`, and `GET /api/v1/devices/{device_uuid}/history`.

- [ ] **Step 1: Write failing incident/history tests**

```python
def test_incidents_are_newest_first_keyset_paginated_and_exclude_destinations(fake_database):
    page = service.list_incidents(limit=1)
    item = page["items"][0]
    assert item == {
        "incident_id": INCIDENT_UUID,
        "device_id": DEVICE_UUID,
        "device_name": "Node",
        "project_name": "Ops",
        "type": "GPU",
        "reason": "driver_unavailable",
        "opened_at": "2026-09-23T10:00:00.000000Z",
        "closed_at": None,
        "status": "ACTIVE",
        "resolution": None,
    }
    assert "destination" not in repr(item).lower()


def test_history_rejects_invalid_range_and_marks_raw_cap_truncation(fake_database):
    with pytest.raises(ValueError, match="Range is invalid"):
        service.device_history(DEVICE_UUID, "8h")
    history = service.device_history(DEVICE_UUID, "7d")
    assert history["truncated"] is True
    assert len(history["cpu"]) <= HISTORY_POINT_CAP


def test_incidents_and_history_are_authorized_no_store_and_not_found_is_404(client):
    assert client.get("/api/v1/incidents").status_code == 401
    assert authorized_client.get(f"/api/v1/devices/{UUID}/history?range=8h").status_code == 422
    assert authorized_client.get(f"/api/v1/devices/{UUID}/history?range=1h").headers["cache-control"] == "no-store"
```

- [ ] **Step 2: Run the new endpoint tests to verify RED**

Run: `..\\.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_stage07_read.py tests/test_dashboard_api.py -q`

Expected: FAIL because the incident/history methods and routes do not exist.

- [ ] **Step 3: Implement bounded incident and history reads**

```python
HISTORY_RANGES = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}


def list_incidents(self, *, limit: int = 50, cursor: str | None = None) -> dict[str, object]:
    # Join Incident -> Device -> Project, sort opened_at DESC then Incident.id DESC,
    # use a descending keyset predicate, fetch limit + 1, and expose no Event/Delivery fields.
    rows = session.execute(statement.limit(limit + 1)).all()
    page = rows[:limit]
    return {
        "items": [_incident_view(incident, device, project) for incident, device, project in page],
        "next_cursor": encode_incident_cursor(_incident_cursor(page[-1])) if len(rows) > limit else None,
        "server_time": _timestamp(now),
    }


def device_history(self, device_uuid: str, range_name: str) -> dict[str, object]:
    # Confirm the device exists, use database UTC time, query `received_at >= now - range`
    # newest-first with limit HISTORY_RAW_CAP + 1, retain most-recent cap, reverse before
    # projection, and return range/from/to/truncated/series_truncated plus bounded series.
    rows = session.scalars(statement.limit(HISTORY_RAW_CAP + 1)).all()
    truncated = len(rows) > HISTORY_RAW_CAP
    retained = list(reversed(rows[:HISTORY_RAW_CAP]))
    return {
        "range": range_name,
        "from": _timestamp(now - HISTORY_RANGES[range_name]),
        "to": _timestamp(now),
        "truncated": truncated,
        **downsample_history(retained),
    }
```

`list_incidents()` returns lifecycle `ACTIVE` when `closed_at is None`, else `CLOSED`; its resolution is stored `close_reason`, not a newly inferred result. `device_history()` returns a 404 through `DashboardNotFound` for a missing device, a safe 422 for unsupported range, and empty series for an existing device with no matching samples. Route static matching keeps `/devices/{device_uuid}/history` before no conflicting dynamic route exists; retain `/alerts` unchanged.

- [ ] **Step 4: Run endpoint and regression tests to verify GREEN**

Run: `..\\.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_stage07_read.py tests/test_dashboard_api.py tests/test_dashboard_read.py tests/test_dashboard_page.py -q`

Expected: PASS; history is bounded, chronological, server-downsampled, and free of raw payload/provider data.

### Task 4: Contract documentation, full verification, and Stage 07.2 checkpoint

**Files:**
- Modify: `docs/API_SPEC.md`
- Modify: `docs/IMPLEMENTATION_STATUS.md`
- Test: `server/tests/test_dashboard_stage07_read.py`
- Test: `server/tests/test_dashboard_api.py`

**Interfaces:**
- Consumes the completed API response fields/endpoints from Tasks 1-3.
- Produces documented query/response bounds and a recoverable Stage 07.2 acceptance checkpoint while retaining Stage 07 as in progress and Stage 07.3 unstarted.

- [ ] **Step 1: Write a failing documentation/status invariant test**

```python
def test_stage07_api_contract_documents_bounded_authenticated_read_endpoints():
    api_spec = (ROOT / "docs" / "API_SPEC.md").read_text(encoding="utf-8")
    assert "GET /api/v1/dashboard/overview" in api_spec
    assert "GET /api/v1/incidents" in api_spec
    assert "range=1h|6h|24h|7d" in api_spec
    assert "maximum page size of 100" in api_spec
```

- [ ] **Step 2: Run the documentation test to verify RED**

Run: `..\\.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider tests/test_dashboard_stage07_read.py -q`

Expected: FAIL because the new bounded Stage 07.2 endpoint contract is undocumented.

- [ ] **Step 3: Document the exact new read contracts and update the checkpoint after evidence**

Document in `docs/API_SPEC.md` the authorization/no-store requirement, allowed filters, default/maximum page sizes, opaque cursor handling, list/incident ordering, display-safe projections, history ranges, 5,000 recent-sample raw cap, 240 returned-point cap, 64-series cap, truncation behavior, and null/missing semantics. Do not document an ORM payload, raw sample JSON, destination, token, or session field.

After successful executable verification, update `docs/IMPLEMENTATION_STATUS.md` to mark Stage 07.2 COMPLETE / ACCEPTED only when all required local checks pass; keep Stage 07 IN PROGRESS, retain Stage 07.3 as the exact next milestone, record no migration, preserve the Stage 06 operator-supplied evidence, and retain real-MySQL/Linux/Docker checks as environment-pending without altering the retained instance.

- [ ] **Step 4: Run full Stage 07.2 verification**

Run from `server`:

```text
..\\.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider -q
..\\.venv\\Scripts\\ruff.exe check --no-cache app tests migrations ..\\scripts
..\\.venv\\Scripts\\ruff.exe format --check --no-cache app tests migrations ..\\scripts
..\\.venv\\Scripts\\mypy.exe app --strict --cache-dir D:\\skybeat\\.stage07-2-mypy-cache
..\\.venv\\Scripts\\python.exe -m alembic heads
..\\.venv\\Scripts\\python.exe -m alembic history
..\\.venv\\Scripts\\python.exe ..\\scripts\\validate_deployment.py
git -C .. diff --check
```

Run from `agent` without modifying agent code:

```text
..\\.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider -q
..\\.venv\\Scripts\\ruff.exe check --no-cache src tests
..\\.venv\\Scripts\\ruff.exe format --check --no-cache src tests
..\\.venv\\Scripts\\mypy.exe src --strict --cache-dir D:\\skybeat\\.stage07-2-agent-mypy-cache
```

Expected: all executable tests/checks pass; the retained real-MySQL tests and unavailable Bash installer checks remain explicit skips only. Do not rerun Docker/Compose or perform database/systemd actions when the environment is unavailable.

## Plan Self-Review

- Spec coverage: Task 1 supplies the bounded cursor/history mechanics; Task 2 covers overview, device list filtering/keysets/projection; Task 3 covers incident and history endpoints; Task 4 documents every contract and runs all requested gates.
- Placeholder scan: no deferred behavior, raw payload response, migration, lifecycle change, credential handling, user-visible UI work, or unbounded read is left unspecified.
- Type consistency: `DashboardReadService` owns the synchronous `overview`, `list_devices`, `list_incidents`, and `device_history` methods; routes only authenticate, validate, call through `asyncio.to_thread`, and translate established query/not-found errors.
- Review focus: malformed cursors, canonical state consistency, keyset ties, incident secret leakage, and bounded sparse history each have named test coverage in Tasks 1-3.
