# Stage 07 Dashboard and Deployment Runbook Design

## Goal

Turn the existing authenticated device-status page into an operational GPU monitoring console and preserve the validated deployment procedure without changing the accepted heartbeat, availability, incident, notification, or device-identity semantics.

## Scope and constraints

- Stage 01 through Stage 06 remain compatible and accepted.
- The dashboard remains server-rendered Jinja2 with same-origin vanilla JavaScript and CSS; no frontend framework or new monitoring subsystem is introduced.
- Existing Google OIDC authorization, opaque session handling, no-store responses, CSP, and DOM text-only insertion remain mandatory.
- Dashboard data comes from existing `Device`, `DeviceLatest`, `HeartbeatSample`, `Incident`, and `AlertEvent` records. It never derives a different availability or GPU-health state.
- The agent deployment path becomes `/opt/skybeat`. The service remains a direct systemd service running as the least-privilege `skybeat` user.
- The repository never stores device credentials, MySQL credentials, Caddy private material, or real device telemetry fixtures.
- Production agent TLS verification remains required. Private-CA trust instructions are explicitly limited to development/LAN testing and never use `verify=False`.
- Stage 07 does not add remote administration, self-healing, a real SMS provider, or Stage 08 work.

## Deployment runbook and safe automation

Create `docs/DEPLOYMENT_RUNBOOK.md` before dashboard application changes. It records the validated development and Ubuntu GPU flow while distinguishing it from production requirements:

- development validation used Windows, isolated MySQL 8.4.10 at loopback port 3307, FastAPI port 8000, and Caddy port 443; production does not depend on those addresses or ports;
- server requirements, protected environment configuration, database creation, Alembic migration, factory-based Uvicorn command, Caddy/HTTPS/firewall configuration, and `/livez`/`/readyz` verification;
- agent install from `agent/` into `/opt/skybeat`, virtual environment/package installation, device enrollment, protected one-time credential transfer to `/etc/skybeat-agent/agent.env`, systemd enablement, heartbeat/database/GPU verification, and no credential display;
- Caddy internal-CA development procedure: install the test root in the Ubuntu system store, then use `SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt` only when required by the local Python trust store; public/system-trusted production certificates remain preferred;
- Caddy outage behavior is a bounded transient agent transport failure, not a reason to weaken TLS;
- backup, restore, upgrade, disable, and smoke procedures remain non-destructive.

Create a root-operated, idempotent `scripts/install-agent.sh` helper. It may create the service user, create `/opt/skybeat/venv`, install the checked-out agent package, place the committed service file, and enable/restart it. It accepts a source directory and a pre-existing protected environment file path; it never accepts a device token as an argument, echoes it, or writes it into shell history. The helper checks required inputs and reports safe actionable errors. The committed unit/template change from `/opt/skybeat-agent` to `/opt/skybeat`.

## Read API design

All new read endpoints are under `/api/v1`, reuse `dashboard_user`, return `Cache-Control: no-store`, and use `DashboardReadService`. They expose projections only, never ORM objects, credentials, session data, token digests, or notification destinations.

### Overview

`GET /api/v1/dashboard/overview` returns current availability counts, GPU-problem count, active-incident count, and bounded project distribution. Counts use the same state projection as the current device list, including `AWAITING_FIRST_HEARTBEAT`; GPU problems exclude `OK` and `NOT MONITORED`.

### Device list

Continue using `GET /api/v1/devices`, adding:

- a validated `gpu_state` filter using existing effective GPU values only;
- opaque keyset cursor pagination ordered by project name, device name, then device UUID;
- a fixed page maximum of 100 and a deliberately bounded response;
- existing project/state/search/disabled filtering and stale-telemetry projection.

The device projection adds only display-safe existing values: primary IP, latest telemetry receipt time, and GPU count. It retains null values instead of creating zeros.

### Device detail, incidents, and history

`GET /api/v1/devices/{device_uuid}` remains the canonical current-device projection. The UI renders it into explicit identity, host, system, storage, GPU, and freshness sections rather than raw JSON.

`GET /api/v1/incidents` returns a bounded, cursor-paginated projection for active/recent incidents with device/project display fields, incident type, current reason, opened/closed timestamps, and resolution information. It uses the durable Stage 03/05 incident lifecycle; JavaScript never calculates incident state.

`GET /api/v1/devices/{device_uuid}/history` accepts only `range=1h|6h|24h|7d`. It reads existing heartbeat samples inside the selected time window and returns a server-downsampled, fixed-size series for CPU, memory, and per-GPU UUID (or index fallback) utilization/temperature where present. The server enforces a raw-read cap and a returned-point cap, emits `truncated` when data exceeds the safe raw bound, and returns null/missing series rather than made-up metrics. Browser history requests never receive unbounded sample payloads.

No Stage 07 migration is planned because `heartbeat_samples` already has the required device/time index and canonical stored payload. If implementation proves a material MySQL performance issue that cannot be safely bounded, stop rather than introduce an unreviewed telemetry schema.

## Dashboard UI design

The existing page remains one Device Status experience:

- header with authenticated identity and logout;
- summary cards for total, ONLINE, SUSPECT, OFFLINE, GPU-problem, and active-incident counts;
- project, availability, GPU-state, and search filters;
- responsive operational device table with text status labels/icons, project, device, hostname, availability, last seen, CPU, memory, GPU health/count, primary IP, agent version, and latest telemetry time;
- clear empty, loading, error, and stale-data states that do not rely on color alone;
- a device detail panel with identity, host/system values, storage, complete GPU inventory, expected GPU policy, and recent incidents;
- bounded SVG charts constructed through DOM APIs for history data, with textual/table alternatives for unavailable or empty series.

Polling remains same-origin, non-overlapping, 15 seconds while visible and 60 seconds while hidden. Failed refreshes retain the last successful timestamp and visibly mark data as potentially stale.

## Testing and acceptance

Tests cover authorization for every new route, invalid history/filter/cursor input, hard limits/pagination, empty/missing telemetry, stale telemetry, GPU state filtering, history downsampling/truncation, incident projections without destinations, escaped page output, runbook safety requirements, and installer refusal to accept unsafe inputs.

Run server and agent regression suites, Ruff, formatting, strict mypy, Alembic history, deployment artifact validation, and whitespace checks. The real Ubuntu GPU smoke test verifies the existing agent to Caddy to API to MySQL to dashboard path with current data, without hardcoding the device. Stage 07 remains in progress until that evidence and executable checks are recorded.

## Real-device Stage 06 evidence to preserve

The user reported a successful real-device validation using an Ubuntu host with an NVIDIA GeForce RTX 5080, NVIDIA driver 595.84, CUDA 13.2 reported by `nvidia-smi`, an agent under `/opt/skybeat`, and a successful HTTPS heartbeat through Caddy to FastAPI/MySQL. Device/latest/receipt/sample records contained ONLINE, GPU OK, CPU, memory, hostname, and GPU-summary data. This is recorded as operator-supplied Stage 06 acceptance evidence without including credentials, private addresses, or raw telemetry.
