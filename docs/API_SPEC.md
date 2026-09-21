# V1 API Specification

Status: approved V1 API architecture baseline.

This document defines the external HTTP contracts between:

* monitoring agents and the server
* administrator browsers and the server

It also defines internal health endpoints used by deployment infrastructure.

All public production communication uses HTTPS.

All timestamps are represented externally as UTC RFC 3339 timestamps.

---

# 1. API Principles

The API follows these principles:

1. Agent and browser authentication are completely separate.
2. Agents can submit telemetry only for their assigned identity.
3. Browser users cannot use their session to impersonate agents.
4. Device credentials cannot access administrator APIs.
5. Project assignment is server-managed.
6. Device names are server-managed.
7. Heartbeats cannot modify project/device configuration.
8. The server is authoritative for availability.
9. Heartbeat acknowledgement occurs only after required database state commits.
10. Notification provider communication never occurs inside heartbeat requests.

---

# 2. Endpoint Overview

| Method | Path                                   | Authentication                | Purpose                            |
| ------ | -------------------------------------- | ----------------------------- | ---------------------------------- |
| POST   | `/api/v1/heartbeats`                   | Device credential             | Submit one telemetry snapshot      |
| GET    | `/api/v1/projects`                     | Browser session               | List projects and status summaries |
| GET    | `/api/v1/devices`                      | Browser session               | List device status                 |
| GET    | `/api/v1/devices/{device_uuid}`        | Browser session               | Get one device's current status    |
| GET    | `/api/v1/devices/{device_uuid}/alerts` | Browser session               | Device alert/delivery history      |
| GET    | `/`                                    | Browser session               | Main Device Status page            |
| GET    | `/auth/google/login`                   | Public/rate-limited           | Start Google authentication        |
| GET    | `/auth/google/callback`                | OAuth transaction             | Complete authentication            |
| POST   | `/auth/logout`                         | Browser session               | End application session            |
| GET    | `/livez`                               | Public minimal                | Process liveness                   |
| GET    | `/readyz`                              | Internal/preferred restricted | Application readiness              |
| GET    | `/internal/worker-health`              | Internal only                 | Worker health/freshness            |
| GET    | `/static/{asset}`                      | Public                        | Static dashboard assets            |

V1 has NO public endpoint for:

* project creation
* project deletion
* device enrollment
* device deletion
* credential creation
* credential rotation
* credential revocation
* expected GPU inventory changes
* monitoring enable/disable
* remote reboot
* remote shell
* arbitrary command execution
* repair
* self-healing

Administrative mutations use the restricted local operator CLI.

---

# 3. Authentication Separation

There are two security domains.

## Agent authentication

Used only for:

`POST /api/v1/heartbeats`

Authentication:

`Authorization: Bearer <device-token>`

---

## Administrator authentication

Used for:

* dashboard
* project reads
* device reads
* alert history

Authentication:

Google OIDC followed by an application session.

A browser session cannot submit agent heartbeats.

A device credential cannot access dashboard APIs.

---

# 4. Device Credential Format

Recommended V1 token format:

```text
sb1.<credential_id>.<secret>
```

Example structure only:

```text
sb1.550e8400-e29b-41d4-a716-446655440000.<random-secret>
```

The secret must contain at least 256 bits of cryptographically secure random entropy.

The server stores:

* credential identifier
* device binding
* secure secret hash
* creation timestamp
* expiry if applicable
* revocation status

The raw secret must never be stored server-side.

Tokens must never appear in:

* URL paths
* query strings
* response bodies
* application logs
* audit metadata
* telemetry payloads

---

# 5. Heartbeat Endpoint

Endpoint:

```http
POST /api/v1/heartbeats
```

Required headers:

```http
Content-Type: application/json
Authorization: Bearer <device-token>
```

Compressed request bodies are not supported in V1.

Maximum request body:

```text
128 KiB
```

The device UUID in the heartbeat must match the device bound to the credential.

---

# 6. Heartbeat Payload

Example:

```json
{
  "schema_version": 1,
  "heartbeat_id": "de8308b2-0a52-4f80-9944-beb045f5e8e2",
  "device_id": "a4f82a6d-61c6-4c72-9a57-626e524571e4",
  "agent_version": "1.0.0",
  "collected_at": "2026-09-21T10:30:00.000Z",

  "hostname": "edge-gpu-01",

  "ip_addresses": [
    "192.0.2.10",
    "2001:db8::10"
  ],

  "os": {
    "name": "Ubuntu",
    "version": "24.04",
    "kernel": "6.8.0-example",
    "architecture": "x86_64"
  },

  "uptime_seconds": 86400,

  "cpu": {
    "utilization_percent": 23.5
  },

  "memory": {
    "total_bytes": 34359738368,
    "used_bytes": 8589934592,
    "available_bytes": 25769803776,
    "utilization_percent": 25.0
  },

  "disks": [
    {
      "device": "/dev/nvme0n1p2",
      "mountpoint": "/",
      "filesystem": "ext4",
      "total_bytes": 107374182400,
      "used_bytes": 42949672960,
      "free_bytes": 64424509440,
      "utilization_percent": 40.0
    }
  ],

  "gpu_health": {
    "state": "OK",
    "reason_code": null,
    "inventory_reliable": true
  },

  "gpus": [
    {
      "index": 0,
      "uuid": "GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      "model": "NVIDIA RTX 4090",
      "driver_version": "example-driver",
      "utilization_percent": 35.0,
      "temperature_celsius": 62.0,
      "memory_total_bytes": 25769803776,
      "memory_used_bytes": 6442450944,
      "health": "OK",
      "reason_code": null
    }
  ]
}
```

The sample values are illustrative.

V1 primarily targets physical NVIDIA GPUs on Linux.

MIG, vGPU and Jetson-specific telemetry require separate validation before being considered fully supported.

---

# 7. Project Information Is NOT Sent by Agent

The heartbeat must NOT contain:

```text
project_id
project_name
device_name
```

These are server-managed.

The server resolves:

```text
authenticated device UUID
        ↓
device record
        ↓
project assignment
```

This prevents an agent from moving itself to another project or renaming itself.

---

# 8. Heartbeat Identity Fields

## schema_version

Type:

integer

V1:

```text
1
```

Unsupported schema versions are rejected.

---

## heartbeat_id

Canonical UUID.

A new UUID is generated for every newly collected snapshot.

The same UUID is reused when retrying that exact snapshot.

---

## device_id

Canonical UUID matching the authenticated device.

Mismatch results in rejection.

---

## agent_version

Non-empty release identifier.

Maximum:

64 characters.

This is informational/versioning metadata and must not replace schema negotiation.

---

## collected_at

UTC RFC 3339 timestamp.

Example:

```text
2026-09-21T10:30:00.000Z
```

This represents when the agent collected the sample.

It is NOT authoritative for device availability.

---

# 9. Host Information

## hostname

Maximum:

253 characters.

Control characters are rejected.

Hostname cannot change the server-managed device name.

---

## ip_addresses

Maximum:

16 entries.

Allowed:

* IPv4
* IPv6

Disallowed:

* hostname
* port
* IPv6 zone identifier

Duplicates are rejected or normalized away according to implementation contract tests.

---

# 10. Operating System

Required object:

```json
{
  "name": "Ubuntu",
  "version": "24.04",
  "kernel": "6.8.0",
  "architecture": "x86_64"
}
```

Each field may be null when genuinely unavailable.

Maximum lengths:

| Field        | Maximum |
| ------------ | ------: |
| name         |     128 |
| version      |     128 |
| kernel       |     128 |
| architecture |      32 |

---

# 11. Uptime

```text
uptime_seconds
```

Type:

nonnegative integer or finite number.

`null` means unavailable.

The value is informational and does not determine server availability state.

---

# 12. CPU

Required structure:

```json
{
  "utilization_percent": 23.5
}
```

Allowed range:

```text
0–100
```

`null` means unavailable.

Zero means a real zero measurement.

---

# 13. Memory

Required structure:

```json
{
  "total_bytes": 34359738368,
  "used_bytes": 8589934592,
  "available_bytes": 25769803776,
  "utilization_percent": 25.0
}
```

All metrics may be null when unavailable.

Rules:

```text
used_bytes <= total_bytes

available_bytes <= total_bytes
```

when relevant values are available.

Do not require:

```text
used + available == total
```

because Linux memory semantics do not guarantee that simple relationship.

---

# 14. Disk Telemetry

Maximum:

```text
64 disk/mount rows
```

Example:

```json
{
  "device": "/dev/nvme0n1p2",
  "mountpoint": "/",
  "filesystem": "ext4",
  "total_bytes": 107374182400,
  "used_bytes": 42949672960,
  "free_bytes": 64424509440,
  "utilization_percent": 40.0
}
```

Mountpoint must be a non-empty absolute Linux path.

Metrics may be null when a known filesystem temporarily cannot be measured.

Do not fabricate zero values.

---

# 15. GPU Telemetry

Maximum:

```text
64 GPUs
```

Each GPU supports:

```text
index

uuid

model

driver_version

utilization_percent

temperature_celsius

memory_total_bytes

memory_used_bytes

health

reason_code
```

---

# 16. GPU Identity

GPU index:

```text
0–1023
```

GPU UUID:

maximum 96 characters.

When available, GPU UUID is the stable identity.

GPU index must not be assumed stable across reboot or driver reload.

---

# 17. GPU Health States

Allowed V1 values:

```text
OK

GPU_MISSING

NVIDIA_SMI_FAILED

DRIVER_ERROR

UNKNOWN
```

The aggregate `gpu_health.state` uses the same vocabulary.

---

# 18. GPU Reason Codes

`reason_code` is:

```text
null
```

when health is `OK`.

Failure reason codes use a finite documented vocabulary defined by `AGENT_SPEC.md`.

Do NOT send arbitrary:

* command output
* stderr
* exception messages
* stack traces

inside `reason_code`.

---

# 19. GPU Inventory Reliability

The heartbeat contains:

```json
"inventory_reliable": true
```

This means the collector believes it successfully observed the complete physical NVIDIA GPU inventory.

Examples:

## Successful query with GPUs

```text
inventory_reliable = true
gpus = [...]
```

## Successful query but no GPU found

```text
inventory_reliable = true
gpus = []
gpu_health = GPU_MISSING
```

## nvidia-smi failure

```text
inventory_reliable = false
gpus = []
gpu_health = NVIDIA_SMI_FAILED
```

Do not reuse stale GPU rows when current inventory could not be reliably queried.

---

# 20. Server-Derived GPU Health

The server maintains GPU policy separately from the agent.

Examples:

```text
gpu_monitoring_enabled

expected_gpu_min_count

expected_gpu_uuids
```

The heartbeat cannot modify these values.

Example:

Expected:

```text
2 GPUs
```

Observed reliably:

```text
1 GPU
```

Effective server health:

```text
GPU_MISSING
```

The server stores both:

* reported GPU health
* effective GPU health

where useful.

---

# 21. CPU-Only Devices

CPU-only devices are explicitly configured:

```text
gpu_monitoring_enabled = false
```

Server UI displays:

```text
NOT MONITORED
```

The agent cannot disable server GPU policy by reporting a local field.

---

# 22. JSON Validation

Schema V1 is strict.

Reject:

* malformed JSON
* duplicate object keys
* non-object root
* invalid Unicode
* non-finite numbers
* excessive nesting
* trailing JSON data
* unsupported fields
* invalid types

Maximum nesting depth:

```text
8
```

Unknown keys are rejected at every level for schema V1 unless explicitly added as backward-compatible optional fields.

---

# 23. Numeric Rules

Percentages:

```text
0 <= value <= 100
```

Temperature:

```text
-100 <= value <= 250
```

Byte counts:

```text
0 <= value <= 2^53 - 1
```

Values must use JSON numeric types.

Do not accept:

```json
"25.5"
```

where a number is required.

JSON booleans must not be accepted as integers.

---

# 24. Null Semantics

`null` means:

```text
measurement unavailable
```

Zero means:

```text
actual measured zero
```

The server and dashboard must preserve this distinction.

---

# 25. Heartbeat Transaction

A new valid heartbeat uses one bounded MySQL/InnoDB transaction.

Conceptually:

```text
BEGIN

authenticate/recheck credential

SELECT device FOR UPDATE

verify monitoring policy

check heartbeat receipt

determine authoritative receipt time

reconcile overdue availability transition

insert heartbeat receipt

insert heartbeat sample

update device_latest

update device last_seen/state

evaluate GPU transition

create/close incident when required

create alert event when required

COMMIT
```

Notification network communication is NOT performed here.

---

# 26. Authoritative Receipt Time

The server receipt time is authoritative for availability.

The implementation must obtain a UTC server/database receipt timestamp after the device state has been serialized for transition processing.

MySQL session/application timezone must be configured consistently as UTC.

Do not use:

* agent clock
* `collected_at`
* browser clock

for availability.

The committed receipt timestamp becomes:

```text
last_seen_at
```

for a new accepted heartbeat.

---

# 27. Heartbeat Acknowledgement

Success:

```http
HTTP/1.1 200 OK
```

Example:

```json
{
  "schema_version": 1,
  "heartbeat_id": "de8308b2-0a52-4f80-9944-beb045f5e8e2",
  "device_id": "a4f82a6d-61c6-4c72-9a57-626e524571e4",
  "accepted_at": "2026-09-21T10:30:00.250Z"
}
```

Success is returned only after transaction commit.

The acknowledgement contains no:

* remote commands
* project configuration
* credential
* expected GPU changes
* repair instruction
* reboot instruction

---

# 28. Heartbeat Idempotency

Unique logical identifier:

```text
(device_id, heartbeat_id)
```

Retention:

at least 24 hours.

The server stores:

* heartbeat ID
* device
* normalized payload hash
* original acknowledgement
* receipt timestamp

---

# 29. Identical Retry

Suppose the first response is lost.

Agent retries:

```text
same heartbeat_id
same snapshot
```

Server returns the original acknowledgement.

The retry must NOT:

* refresh `last_seen_at`
* create another telemetry sample
* modify latest telemetry
* change GPU streaks
* create another event

---

# 30. Conflicting Retry

If:

```text
same heartbeat_id
different normalized payload
```

return:

```http
409 Conflict
```

Error code:

```text
heartbeat_id_conflict
```

No state is changed.

---

# 31. Payload Hash

Idempotency uses a SHA-256 digest of the validated normalized payload.

Normalization must ensure irrelevant JSON formatting differences do not create false conflicts.

For example:

```json
{"a":1,"b":2}
```

and equivalent whitespace/key formatting should normalize consistently.

Array ordering remains significant.

---

# 32. Credential Revalidation on Retry

An old heartbeat acknowledgement is not accessible merely because its heartbeat ID exists.

Authentication is checked again.

A revoked credential must not retrieve an acknowledgement after revocation.

---

# 33. Availability

Initial defaults:

```text
age < 75 seconds
    ONLINE

75 <= age < 180 seconds
    SUSPECT

age >= 180 seconds
    OFFLINE
```

Availability is based on the latest committed NEW heartbeat.

Duplicate retries do not refresh availability.

---

# 34. First Heartbeat

Newly enrolled devices have:

```text
last_seen_at = null
```

and are represented as:

```text
AWAITING_FIRST_HEARTBEAT
```

or equivalent derived UI state.

If first contact occurs before the offline threshold:

```text
→ ONLINE
```

without recovery event.

If the device has already entered an OFFLINE incident before its first successful contact:

```text
→ ONLINE
```

and the incident may close according to `ALERTING.md`.

---

# 35. Worker Freshness

Device status APIs include enough information for the UI to know whether background health evaluation itself is healthy.

Example:

```json
{
  "worker_healthy": true
}
```

The dashboard must not continue presenting cached green status without indicating that health evaluation is stale.

---

# 36. GET /api/v1/projects

Authentication:

authorized browser session.

Purpose:

Provide project grouping/filter information.

Example response:

```json
{
  "items": [
    {
      "project_id": "b71a9d41-3aa4-41aa-b27e-4a8e07a18c12",
      "name": "StarAgri",
      "description": "StarAgri GPU devices",
      "is_active": true,

      "device_counts": {
        "total": 10,
        "online": 8,
        "suspect": 1,
        "offline": 1,
        "awaiting_first_heartbeat": 0
      }
    }
  ],
  "server_time": "2026-09-21T10:30:00Z"
}
```

This endpoint is read-only.

---

# 37. GET /api/v1/devices

Authentication:

authorized browser session.

Supported query parameters:

```text
limit
cursor
project_id
state
include_disabled
search
```

`limit`:

```text
default 50
minimum 1
maximum 100
```

`state` may be:

```text
ONLINE
SUSPECT
OFFLINE
AWAITING_FIRST_HEARTBEAT
```

`project_id` filters devices by project.

`search` may search safe server-managed/display fields such as:

* device name
* hostname
* device UUID

Search implementation must remain bounded.

---

# 38. Device List Ordering

Default ordering should favor operational usefulness while remaining pagination-safe.

Recommended initial ordering:

```text
project name
device name
device UUID
```

Cursor values must be opaque to clients.

Do not expose raw SQL offsets or implementation internals through cursor encoding.

For the initial 100-device fleet, conventional bounded pagination is sufficient; implementation should prioritize correctness and simplicity.

---

# 39. Device List Response

Example:

```json
{
  "items": [
    {
      "device_id": "a4f82a6d-61c6-4c72-9a57-626e524571e4",

      "project": {
        "project_id": "b71a9d41-3aa4-41aa-b27e-4a8e07a18c12",
        "name": "StarAgri"
      },

      "name": "Warehouse-GPU-01",

      "hostname": "edge-gpu-01",

      "ip_addresses": [
        "192.0.2.10"
      ],

      "monitoring_enabled": true,

      "state": "ONLINE",

      "pending_first_heartbeat": false,

      "last_seen_at": "2026-09-21T10:30:00Z",

      "telemetry_stale": false,

      "agent_version": "1.0.0",

      "uptime_seconds": 86400,

      "cpu": {
        "utilization_percent": 23.5
      },

      "memory": {
        "utilization_percent": 25.0
      },

      "disks": [
        {
          "mountpoint": "/",
          "utilization_percent": 40.0
        }
      ],

      "gpu_health": {
        "reported": "OK",
        "effective": "OK"
      },

      "gpus": [
        {
          "index": 0,
          "uuid": "GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
          "model": "NVIDIA RTX 4090",
          "utilization_percent": 35.0,
          "temperature_celsius": 62.0,
          "memory_total_bytes": 25769803776,
          "memory_used_bytes": 6442450944,
          "health": "OK"
        }
      ]
    }
  ],

  "next_cursor": null,

  "server_time": "2026-09-21T10:30:05Z",

  "worker_healthy": true
}
```

---

# 40. Missing Snapshot

If a device has never sent telemetry:

```text
last_seen_at = null

hostname = null

ip_addresses = []

cpu = null

memory = null

disks = []

gpus = []
```

Do not fabricate zeros.

---

# 41. Stale Telemetry

An OFFLINE device may still have a latest snapshot.

Example:

```text
Device: OFFLINE

Last seen:
18 minutes ago

CPU:
23% (STALE)

GPU:
OK (STALE)
```

API therefore exposes:

```text
telemetry_stale = true
```

where appropriate.

The dashboard must not present stale measurements as current.

---

# 42. GET /api/v1/devices/{device_uuid}

Returns the current detailed snapshot for one device.

Includes:

* project
* device name
* UUID
* hostname
* IP addresses
* OS
* agent version
* monitoring status
* availability
* last seen
* telemetry freshness
* CPU
* full memory metrics
* all disks
* all GPUs
* reported GPU health
* effective GPU health
* expected GPU policy
* uptime
* recent operational status if appropriate

Credentials are never returned.

---

# 43. GET /api/v1/devices/{device_uuid}/alerts

Returns paginated event/delivery history.

Example event:

```json
{
  "event_id": "7c515a39-df21-4f0e-8206-cd684814bbcb",

  "incident_id": "3ca66111-53d0-46f8-a7ae-9f85db764c18",

  "type": "DEVICE_OFFLINE",

  "occurred_at": "2026-09-21T10:20:00Z",

  "resolved_at": "2026-09-21T10:27:00Z",

  "deliveries": [
    {
      "channel": "EMAIL",
      "status": "ACCEPTED",
      "attempt_count": 1
    },

    {
      "channel": "SMS",
      "status": "FAILED",
      "attempt_count": 6,
      "last_error_code": "provider_timeout"
    }
  ]
}
```

Do not expose full recipient addresses unnecessarily.

Masked representations may be used.

---

# 44. Browser Cache Policy

Authenticated dashboard/API responses use:

```http
Cache-Control: no-store
```

Do not enable permissive cross-origin access.

Dashboard API requests are same-origin.

---

# 45. Dashboard Polling

Default:

```text
15 seconds
```

Polling must not overlap.

When the browser tab is hidden, polling may:

* slow
* pause

After failed refreshes, display:

* last successful update
* stale/error indication

Do not silently leave old status appearing current.

---

# 46. Google Login

Endpoint:

```http
GET /auth/google/login
```

Begins authorization-code flow.

Requirements include:

* state
* nonce
* PKCE where supported/appropriate
* secure browser binding
* short-lived OAuth transaction

---

# 47. Google Callback

Endpoint:

```http
GET /auth/google/callback
```

Validate:

* state
* nonce
* issuer
* audience
* token signature
* token lifetime
* verified identity
* configured authorization policy

Then check:

```text
email allowlist
```

and/or:

```text
approved hosted domain
```

Valid Google authentication without authorization results in denial.

---

# 48. Logout

Endpoint:

```http
POST /auth/logout
```

Requires:

* valid application session
* CSRF protection where applicable

Server revokes the session.

Response:

```http
204 No Content
```

---

# 49. Liveness

Endpoint:

```http
GET /livez
```

Response:

```json
{
  "status": "ok"
}
```

This indicates the API process can respond.

It does NOT prove:

* MySQL is healthy
* worker is healthy
* SMTP is healthy
* SMS is healthy

---

# 50. Readiness

Endpoint:

```http
GET /readyz
```

Readiness may verify:

* MySQL connectivity
* expected schema/migration compatibility
* critical application initialization

Failure:

```http
503 Service Unavailable
```

The endpoint should normally be restricted to the deployment/internal network where practical.

---

# 51. Worker Health

Endpoint:

```http
GET /internal/worker-health
```

Internal only.

May expose safe fields such as:

```json
{
  "status": "ok",
  "last_health_sweep_at": "2026-09-21T10:30:05Z",
  "last_delivery_poll_at": "2026-09-21T10:30:04Z"
}
```

No:

* credentials
* provider secrets
* database URLs
* stack traces

---

# 52. Standard Error Shape

Server-generated application errors use:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Heartbeat payload is invalid.",
    "request_id": "895e3612-340b-4985-bf1f-7bc11f73433c",

    "fields": [
      {
        "path": "cpu.utilization_percent",
        "code": "out_of_range"
      }
    ]
  }
}
```

Never include rejected secrets or raw sensitive values.

---

# 53. Agent HTTP Behavior

| Status | Meaning                        | Agent behavior                          |
| ------ | ------------------------------ | --------------------------------------- |
| 400    | Malformed request              | Drop sample, log safe category          |
| 401    | Invalid/revoked credential     | Stop fast retry; slow bounded probe     |
| 403    | Identity/policy rejection      | Stop fast retry; operator-visible error |
| 404    | Wrong route/configuration      | Treat as configuration issue            |
| 405    | Unsupported method             | Programming/configuration error         |
| 408    | Request timeout                | Bounded retry                           |
| 409    | Heartbeat ID conflict          | Drop; programming error                 |
| 413    | Payload too large              | Drop; local serialization/config issue  |
| 415    | Wrong content type             | Drop                                    |
| 422    | Contract/schema failure        | Drop incompatible sample                |
| 429    | Rate limited                   | Respect bounded Retry-After             |
| 500    | Server failure                 | Bounded retry                           |
| 502    | Gateway failure                | Bounded retry                           |
| 503    | Dependency/service unavailable | Bounded retry                           |
| 504    | Gateway timeout                | Bounded retry                           |

Agents must branch primarily on status/error code, not English message text.

---

# 54. TLS Failure

Certificate verification failure must never cause the agent to:

```text
disable TLS verification
```

or fall back to:

```text
plain HTTP
```

The failure should become operator-visible.

---

# 55. Agent Request Deadline

Initial total HTTP attempt deadline:

```text
10 seconds
```

This includes as much as practical:

* DNS
* connection
* TLS
* send
* response

Retries are bounded.

The agent must never wait indefinitely.

---

# 56. Server Deadlines

Server operations must also be bounded.

Initial implementation targets may include:

```text
database lock wait:
approximately 1 second

database statement:
approximately 3 seconds

heartbeat handler:
approximately 5 seconds
```

Exact values should be tested against MySQL 8.x and production VM characteristics.

Timeouts must not compromise transaction correctness.

A timeout may leave the agent uncertain whether a request committed, which is why heartbeat idempotency is required.

---

# 57. Rate Limiting

Normal heartbeat rate:

```text
approximately 2/minute/device
```

because the default interval is 30 seconds.

Initial per-device allowance:

```text
6 requests/minute

burst 6
```

This leaves room for:

* retry
* jitter
* credential rotation

Rate limiting must not use raw secret values as keys.

---

# 58. Shared NAT

Multiple edge devices may appear from the same source IP.

Therefore source-IP rate limiting must NOT assume:

```text
one IP = one device
```

Any pre-authentication IP limit must comfortably support the initial fleet behind shared NAT/VPN.

The device credential remains the primary authenticated rate-limit identity.

---

# 59. Rate-Limit Architecture

For the initial single-VM / ~100-device deployment, do not introduce Redis solely for rate limiting.

Rate limiting may use an appropriate bounded single-deployment strategy consistent with `SECURITY.md`.

If API horizontal scaling is introduced later, rate-limit coordination must be revisited.

Rate limits must never create device-presence evidence.

A rejected heartbeat does not refresh `last_seen_at`.

---

# 60. Request IDs

The server generates trusted request IDs.

Do not blindly trust a client-supplied request ID as an authoritative log correlation identifier.

Request IDs may be returned in error responses and safe response headers.

---

# 61. Production API Documentation

Interactive API documentation should not be publicly exposed in production by default.

Development environments may enable:

* OpenAPI
* Swagger UI

as appropriate.

---

# 62. Schema Compatibility

Heartbeat:

```text
schema_version = 1
```

is strict.

Backward-compatible optional additions require:

1. server support first
2. agent rollout second

Changes to:

* required fields
* units
* identity semantics
* existing field meaning
* removed fields

require a new schema version.

---

# 63. Agent Version vs Schema Version

These are different.

Example:

```text
agent_version = 1.4.2

schema_version = 1
```

Several agent releases may use the same wire schema.

Do not dispatch parsing behavior solely from `agent_version`.

---

# 64. Telemetry Persistence

Every accepted heartbeat stores:

```text
schema_version
```

with the historical sample.

This permits future compatibility investigation.

---

# 65. API Security Requirements

All external input is untrusted.

Validate:

* body size
* JSON structure
* field count
* array size
* string length
* numeric bounds
* UUID syntax
* IP syntax
* timestamps
* authorization
* device identity

Never use device-provided strings directly as:

* SQL
* HTML
* shell commands
* filesystem paths for server operations

---

# 66. HTML Safety

Device-supplied:

* hostname
* OS strings
* filesystem names
* GPU model strings

must be HTML escaped when displayed.

Example hostile hostname:

```html
<script>alert(1)</script>
```

must appear as text, never execute.

---

# 67. Sensitive Fields

Browser APIs must never expose:

* credential hashes
* device raw secrets
* SMTP password
* SMS API keys
* Google client secret
* OAuth raw tokens
* application session hashes
* database credentials

---

# 68. MySQL Integration Requirements

API integration tests must use the selected MySQL 8.x version.

Test real:

* InnoDB transactions
* `SELECT ... FOR UPDATE`
* unique constraints
* JSON storage
* transaction rollback
* lock timeout behavior
* connection loss
* duplicate heartbeat races
* worker/API concurrency

SQLite is not an acceptable substitute for these integration tests.

---

# 69. Required Heartbeat Contract Tests

Tests must cover:

* valid example
* minimum valid payload
* maximum allowed body
* body too large
* malformed JSON
* duplicate JSON keys
* unknown field
* excessive nesting
* invalid Unicode
* NaN/infinity rejection
* invalid UUID
* invalid IP
* invalid timestamp
* percentage below zero
* percentage above 100
* negative byte count
* invalid temperature
* too many disks
* duplicate mountpoint
* too many GPUs
* duplicate GPU UUID
* duplicate GPU index
* nullable unavailable metrics

---

# 70. Authentication Tests

Test:

* missing token
* malformed token
* unknown credential
* incorrect secret
* expired credential
* revoked credential
* device UUID mismatch
* rotation overlap
* browser session used against heartbeat endpoint
* device token used against browser endpoint

---

# 71. Idempotency Tests

Test:

```text
same heartbeat + same payload

same heartbeat + different payload

two concurrent identical requests

two concurrent conflicting requests

response lost after commit

retry after device becomes offline

retry after credential revoked

receipt expiry
```

Identical duplicates must not refresh presence.

---

# 72. Availability Tests

Test exact boundaries:

```text
74.999 seconds

75 seconds

179.999 seconds

180 seconds
```

Also test:

* never-seen device
* first heartbeat
* late heartbeat
* worker delay
* worker restart
* API restart
* MySQL restart
* duplicate after OFFLINE

---

# 73. GPU Contract Tests

Test:

* zero GPU
* one GPU
* multiple GPUs
* GPU reorder
* expected GPU missing
* nvidia-smi missing
* nvidia-smi timeout
* driver failure
* malformed output
* partial unavailable metrics
* reliable empty inventory
* unreliable inventory
* CPU-only device
* duplicate heartbeat not advancing debounce

---

# 74. Project API Tests

Test:

* multiple projects
* project with zero devices
* project with online/offline mixture
* project filtering
* inactive project behavior
* device reassignment
* history preserved after reassignment
* project assignment not modifiable through heartbeat

---

# 75. Browser Tests

Test:

* authorized Google account
* unauthorized valid Google account
* expired session
* revoked session
* device list
* project grouping
* project filter
* state filter
* search
* multiple GPUs
* multiple disks
* stale telemetry
* null telemetry
* never-seen device
* hostile device-provided strings
* refresh failure
* worker unhealthy state

---

# 76. Failure Tests

Test:

* API unavailable
* MySQL unavailable
* MySQL restarted
* database transaction rollback
* worker unavailable
* Caddy unavailable
* SMTP unavailable
* SMS unavailable
* Google authentication unavailable

Failures in one subsystem should not unnecessarily break unrelated functionality.

---

# 77. Production Acceptance

The API portion of V1 is production-ready only after:

* HTTPS works
* device credentials are isolated per device
* credential revocation works
* Google authorization works
* MySQL transaction tests pass
* heartbeat idempotency passes
* project filtering works
* stale telemetry is represented correctly
* rate limiting is tested
* payload limits are enforced
* no sensitive fields leak
* API/worker race tests pass
* edge-to-server failure drills pass

Passing unit tests alone does not establish production readiness.

---

# 78. V1 Contract Summary

The agent is responsible for:

```text
collect
classify local observation
send
retry safely
```

The server is responsible for:

```text
authenticate
validate
persist
determine presence
apply expected GPU policy
create incidents
notify
authorize administrators
organize devices into projects
```

The agent does NOT decide:

```text
project assignment
device display name
server availability state
alert recipients
notification policy
expected GPU baseline
```

This separation is a core V1 architectural rule.
