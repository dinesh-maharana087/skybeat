# V1 Architecture

Status: approved architecture baseline for V1 development.

Target: up to 100 monitored devices on one Ubuntu VM.

This is a standalone device and GPU monitoring/alerting platform and has no dependency on Canopus.

---

# 1. Purpose

The platform provides centralized monitoring of Linux edge devices and NVIDIA GPU systems.

Its primary responsibilities are:

* organize devices into projects
* maintain secure device identities
* receive periodic agent heartbeats
* collect system telemetry
* collect NVIDIA GPU telemetry
* determine device availability centrally
* detect GPU observation failures
* persist operational history
* display current device status
* notify administrators about outages
* notify administrators when devices recover

Monitoring is read-only.

V1 does NOT provide:

* remote shell
* remote command execution
* remote reboot
* operating-system changes
* automatic remediation
* self-healing

---

# 2. Important Monitoring Semantics

A missing heartbeat means:

CONTACT LOST

It does not prove that the physical machine itself is powered off.

Possible causes include:

* device powered off
* operating-system failure
* agent failure
* network failure
* VPN/routing failure
* server connectivity failure

The dashboard and notifications must therefore use wording such as:

Device offline / contact lost

rather than claiming a specific hardware failure.

Likewise:

GPU OK

means the configured GPU telemetry checks succeeded.

It does not constitute a comprehensive hardware diagnostic.

---

# 3. High-Level Architecture

```text
                          INTERNET / PRIVATE NETWORK
                                   │
                                   │ HTTPS :443
                                   ▼
                            ┌─────────────┐
                            │    Caddy    │
                            │ TLS / Proxy │
                            └──────┬──────┘
                                   │
                    ┌──────────────┴───────────────┐
                    │                              │
                    ▼                              ▼
             ┌──────────────┐               Administrator
             │   FastAPI    │                  Browser
             │    Server    │
             └──────┬───────┘
                    │
                    │
              ┌─────▼──────┐
              │  MySQL 8   │
              │ Database   │
              └─────▲──────┘
                    │
                    │
             ┌──────┴───────┐
             │ Health/Alert │
             │    Worker    │
             └──────┬───────┘
                    │
             ┌──────┴───────┐
             │              │
             ▼              ▼
          Email            SMS
          SMTP          Provider API


EDGE DEVICES

┌────────────────────┐
│ Linux GPU Device   │
│                    │
│ Monitoring Agent   │
│ systemd service    │
└─────────┬──────────┘
          │
          │ HTTPS heartbeat
          │ every ~30 sec
          ▼
        Caddy
```

---

# 4. Architectural Style

V1 uses a:

MODULAR MONOLITH

The central server consists of one application codebase with two runtime entry points:

1. API process
2. Worker process

They share:

* domain models
* configuration
* database layer
* business logic

but do NOT depend on shared process memory.

Conceptually:

```text
Server Package
│
├── API Process
│
└── Worker Process
```

The API handles:

* heartbeats
* authentication
* dashboard requests
* read APIs
* Google authentication

The worker handles:

* availability sweeps
* incident creation
* alert materialization
* notification delivery
* retry processing
* retention cleanup

---

# 5. Why Not Microservices?

The initial target is approximately:

100 devices

with:

30-second heartbeats.

That represents approximately:

200 heartbeats/minute

or:

3.33 heartbeats/second.

This load does not justify:

* Kubernetes
* Kafka
* RabbitMQ
* Redis
* Celery
* distributed databases
* separate microservices
* time-series infrastructure

Adding those components would increase:

* operational complexity
* failure modes
* deployment complexity
* maintenance burden

without solving a demonstrated V1 requirement.

---

# 6. Core Technology

Server:

* Ubuntu 24.04 LTS
* Python 3.12
* FastAPI
* Pydantic 2
* SQLAlchemy 2
* Alembic
* MySQL 8.x
* MySQL-compatible Python driver
* Uvicorn
* Jinja2

Agent:

* Python 3.12 where available
* psutil
* NVIDIA `nvidia-smi`
* systemd

Infrastructure:

* Docker
* Docker Compose
* Caddy

Authentication:

* Google OIDC/OAuth

Notifications:

* SMTP
* provider-independent SMS adapter

Exact package versions are locked during implementation.

---

# 7. Reverse Proxy

Caddy is the preferred V1 reverse proxy.

Responsibilities:

* HTTPS termination
* automatic TLS certificate lifecycle
* HTTP → HTTPS redirect
* request-size protection
* forwarding to FastAPI
* security headers where appropriate

Only Caddy should normally expose public application ports.

Typical external exposure:

```text
80
443
```

MySQL must NOT be publicly exposed.

---

# 8. Dashboard Architecture

V1 uses:

Jinja2 templates + CSS + small JavaScript

instead of a separate SPA framework.

There is no React/Vue frontend service in V1.

The browser periodically requests status updates from the FastAPI server.

Initial polling interval:

15 seconds.

Advantages:

* simple deployment
* no separate frontend build pipeline
* simpler Google authentication
* same-origin API access
* fewer moving parts

A SPA may be introduced later if dashboard complexity genuinely requires it.

---

# 9. Organizational Model

The primary hierarchy is:

```text
Project
│
├── Device
│   │
│   ├── Identity
│   ├── Credentials
│   ├── Latest Telemetry
│   ├── Heartbeat History
│   ├── GPU(s)
│   ├── Incidents
│   └── Alerts
│
├── Device
│
└── Device
```

Projects are organizational.

They do NOT participate in device authentication.

---

# 10. Project Identity

A project represents a logical grouping of monitored devices.

Examples:

```text
StarAgri

Arya Warehouse

Development Lab

Client ABC
```

Each project contains:

* internal project ID
* project name
* optional description
* active/inactive state
* created timestamp
* updated timestamp

A project may contain multiple devices.

---

# 11. Device Identity

Three different concepts must remain separate.

## Device UUID

Permanent technical identity.

Example:

```text
8cf5c647-70a0-4559-a4da-1a39dd66c119
```

Used for:

* authentication binding
* telemetry ownership
* history
* incidents
* stable device identity

Changing project or device name must NOT change this UUID.

---

## Device Name

Human-readable administrator label.

Example:

```text
Warehouse-GPU-01
```

It may be renamed.

It is NOT an authentication identity.

---

## Hostname

Reported by the operating system.

Example:

```text
assertai-gpu-023
```

It may change independently of the configured device name.

---

# 12. Device Reassignment

A device belongs to one project in V1.

Changing:

```text
Project A
    Device-X
```

to:

```text
Project B
    Device-X
```

must preserve:

* device UUID
* credentials
* heartbeat history
* incidents
* alert history
* telemetry history

Only `project_id` changes.

Project reassignment should create an audit event.

---

# 13. Device Enrollment

V1 uses a restricted local operator CLI.

There is no public device-enrollment API.

Example conceptual workflow:

```text
Operator
   │
   ├── create project
   │
   └── enroll device
           │
           ├── select project
           ├── set device name
           ├── generate device UUID
           └── generate credential
```

The operator then installs the generated configuration on the device.

Example:

```text
SERVER_URL=https://monitor.example.com
DEVICE_UUID=...
DEVICE_TOKEN=...
```

The agent does not need to know:

* project database ID
* project name
* database structure

The server determines project assignment from the authenticated device UUID.

---

# 14. Device Authentication

Every device receives its own credential.

A fleet-wide shared credential is prohibited.

Conceptually:

```text
DEVICE UUID
      │
      └── DEVICE CREDENTIAL
```

Credentials must be:

* securely generated
* stored hashed server-side
* independently revocable
* independently rotatable

Raw credentials must never appear in:

* logs
* database audit metadata
* source code
* Git
* error messages

Credential rotation may temporarily permit old and new credentials simultaneously for a bounded migration period.

---

# 15. Heartbeat Flow

The agent periodically collects telemetry and sends:

```text
Agent
   │
   │ POST /api/v1/heartbeat
   ▼
Caddy
   │
   ▼
FastAPI
   │
   ├── request-size validation
   ├── authenticate device
   ├── schema validation
   ├── lock/read device state
   ├── duplicate detection
   ├── record server receipt time
   ├── persist telemetry
   ├── update latest snapshot
   ├── evaluate state transitions
   └── COMMIT
          │
          ▼
       HTTP 200
```

The API must never acknowledge a heartbeat as successful before the required database transaction commits.

---

# 16. Authoritative Time

Availability uses SERVER receipt time.

Agent-provided:

```text
collected_at
```

is diagnostic only.

It must never determine whether a device is ONLINE/OFFLINE.

This protects availability calculations from:

* incorrect edge-device clocks
* timezone configuration errors
* unsynchronized edge systems

All application timestamps are treated as UTC.

MySQL timestamps used for operational state should be stored consistently in UTC.

The application must explicitly configure and verify database/session timezone behavior.

---

# 17. Heartbeat Idempotency

Each heartbeat contains:

```text
heartbeat_id
```

generated by the agent.

The server stores short-lived heartbeat receipts for duplicate detection.

If an agent retries the exact same heartbeat because it did not receive the original response:

```text
same device
same heartbeat_id
same payload
```

the server returns the previously recorded result.

The duplicate must NOT:

* refresh last-seen time
* create another sample
* increment GPU state streaks
* create another incident

If:

```text
same heartbeat_id
different payload
```

is received, return:

```text
409 Conflict
```

The initial deduplication window is 24 hours.

---

# 18. MySQL Transaction Strategy

MySQL 8.x with InnoDB is required.

State-changing operations use transactions.

For state transitions involving a device, the application should lock the device row using an appropriate SQLAlchemy/MySQL equivalent of:

```sql
SELECT ...
FOR UPDATE
```

The transaction then re-reads authoritative state before calculating transitions.

This protects against races between:

* heartbeat processing
* availability sweeper
* concurrent API requests

Do not hold device locks while calling:

* SMTP
* SMS providers
* Google
* any external network service

External network I/O must happen outside these critical transactions.

---

# 19. Availability State Machine

Availability is calculated centrally.

States:

```text
ONLINE
SUSPECT
OFFLINE
```

Recovery is an event, not a persistent availability state.

Initial thresholds:

```text
Heartbeat age < 75 seconds
    ONLINE

Heartbeat age >= 75 seconds
and < 180 seconds
    SUSPECT

Heartbeat age >= 180 seconds
    OFFLINE
```

Health sweep:

```text
every 5 seconds
```

All thresholds are configurable.

---

# 20. Never-Seen Device

A newly enrolled device may not yet have contacted the server.

This must not immediately appear as a normal outage.

Represent it separately as:

```text
AWAITING_FIRST_HEARTBEAT
```

or equivalent UI semantics.

The exact database representation may use:

* `last_seen_at = NULL`
* monitoring start timestamp
* derived status

without requiring an additional persistent availability enum if unnecessary.

---

# 21. Recovery

When a device transitions:

```text
OFFLINE
    ↓
heartbeat received
    ↓
ONLINE
```

the server:

1. closes the active availability incident
2. records a recovery event
3. updates device state
4. schedules recovery notifications

A device's first-ever heartbeat is NOT a recovery.

---

# 22. GPU State

GPU state is independent from device availability.

Example:

```text
Device: ONLINE
GPU: DRIVER_ERROR
```

is valid.

Likewise:

```text
Device: OFFLINE
GPU: OK (STALE)
```

means the last known GPU observation was OK, but that observation is no longer current.

---

# 23. GPU Identity

Multiple GPUs are supported.

Where available, use:

```text
GPU UUID
```

as stable GPU identity.

GPU index must NOT be treated as stable identity because indices may change.

Example:

```text
GPU 0 → UUID GPU-a
GPU 1 → UUID GPU-b
```

after reboot could become:

```text
GPU 0 → UUID GPU-b
GPU 1 → UUID GPU-a
```

This is not a GPU disappearance.

---

# 24. GPU Health

Supported V1 states include:

```text
OK

GPU_MISSING

NVIDIA_SMI_FAILED

DRIVER_ERROR

UNKNOWN
```

GPU monitoring is configurable per device.

CPU-only devices explicitly have GPU monitoring disabled.

Disabled monitoring must appear as:

```text
NOT MONITORED
```

rather than `OK`.

---

# 25. Expected GPU Inventory

GPU devices may define:

```text
expected_gpu_min_count
```

and optionally:

```text
expected_gpu_uuids
```

Example:

```text
expected_gpu_min_count = 2

expected_gpu_uuids =
GPU-aaaa
GPU-bbbb
```

If only one appears:

```text
GPU_MISSING
```

or equivalent degraded state is generated.

The system must never automatically reduce the expected baseline simply because a GPU disappears.

Baseline changes require an administrative action.

---

# 26. GPU Notification Policy

V1 architecture supports GPU degradation/recovery events.

Recommended behavior:

```text
Healthy
   │
   ├── one bad sample
   │       wait
   │
   └── second consecutive bad sample
           ↓
       GPU incident
```

Recovery similarly requires two qualifying healthy observations.

This reduces alerts from transient `nvidia-smi` failures.

GPU alert delivery may be enabled after device offline/recovery notification behavior is validated.

---

# 27. Worker Architecture

The worker runs independently from the API process.

Conceptual loops:

```text
Worker
│
├── Availability Sweep
│
├── Alert Materialization
│
├── Notification Delivery
│
└── Retention Cleanup
```

One worker is sufficient for V1.

Database constraints and transactional locking must still protect correctness if a second worker accidentally starts.

---

# 28. Availability Sweep

Approximately every five seconds:

```text
SELECT monitored devices
that may have crossed a threshold
```

For candidate devices:

```text
BEGIN

lock device

re-read last_seen_at

calculate current state

apply transition if necessary

create/close incident

create event if necessary

COMMIT
```

The sweep must not send email or SMS directly.

---

# 29. Incident Model

An incident represents a continuing problem.

Examples:

```text
AVAILABILITY incident

GPU incident
```

An outage should create:

```text
Incident
   │
   ├── OFFLINE event
   │
   └── RECOVERY event
```

rather than creating unrelated outage records every sweep.

Only one open incident of a given type may exist for a device at a time.

This invariant must be enforced transactionally in MySQL.

Because MySQL does not provide PostgreSQL-style partial unique indexes, this rule must NOT depend on a PostgreSQL partial-index design.

Use an explicit MySQL-compatible strategy such as:

* transactional locking plus a generated active key/column with uniqueness

or another migration-tested equivalent.

The exact implementation must be documented before the incident migration is created.

---

# 30. Notification Pipeline

Notification delivery is asynchronous relative to heartbeat ingestion.

```text
State Transition
      │
      ▼
Alert Event
      │
      ▼
Notification Delivery Row
      │
      ▼
Worker
      │
      ├── SMTP
      │
      └── SMS
```

A provider failure must never roll back a heartbeat.

---

# 31. Notification Provider Interface

Conceptually:

```python
NotificationProvider
    send(notification)
```

Implementations:

```text
SMTPEmailProvider

SMSProvider
```

SMS provider implementation must remain replaceable.

Possible future adapters:

```text
Twilio

Indian DLT-compatible provider

Other approved provider
```

The alert engine must not contain provider-specific business logic.

---

# 32. Notification Deduplication

One continuing outage:

```text
ONLINE
→ OFFLINE
```

creates one outage incident/event.

Repeated sweeps while still offline:

```text
OFFLINE
→ OFFLINE
```

must NOT generate new outage alerts.

After:

```text
OFFLINE
→ ONLINE
```

a recovery event is created.

A later:

```text
ONLINE
→ OFFLINE
```

creates a new incident.

---

# 33. Notification Delivery State

Suggested states:

```text
PENDING

PROCESSING

RETRY_WAIT

ACCEPTED

FAILED

CANCELLED
```

Delivery attempts are persisted.

Important information includes:

* event
* channel
* recipient
* provider
* attempt count
* next retry
* last error category
* provider message ID when available
* timestamps

Raw provider responses containing sensitive information must not be stored.

---

# 34. Stale Outage Notifications

Suppose:

```text
18:00 Device OFFLINE

18:00 Email provider unavailable

18:03 Device RECOVERS

18:04 Email provider becomes available
```

The system must not blindly send:

```text
DEVICE OFFLINE
```

after recovery as though the outage were current.

Queued obsolete outage deliveries should be:

```text
CANCELLED
```

or otherwise explicitly superseded.

Recovery communication may include information about the completed outage.

---

# 35. Google Authentication

Google OIDC authenticates dashboard users.

Authentication does not imply authorization.

After successful Google authentication, verify:

```text
email allowlist
```

and/or:

```text
approved Workspace domain
```

Example:

```text
Google login valid
        │
        ▼
Email/domain authorized?
        │
   ┌────┴─────┐
   │          │
  YES         NO
   │          │
Dashboard   DENY
```

Default policy is deny.

---

# 36. Browser Sessions

After successful authorization, issue an opaque application session.

Session cookies should use:

```text
Secure

HttpOnly

SameSite
```

as appropriate.

Store only a hash of the opaque session token server-side.

Sessions require:

* expiry
* revocation
* inactivity handling where configured

OAuth temporary state/nonce information must be short-lived and single-use.

---

# 37. Dashboard

V1 contains one main page:

```text
DEVICE STATUS
```

Example:

```text
---------------------------------------------------------------
GPU MONITOR
---------------------------------------------------------------

Project: StarAgri                         9 / 10 Online

Device             State       CPU     RAM     GPU       Temp
----------------------------------------------------------------
WH-GPU-01          ONLINE      21%     42%     OK        51°C
WH-GPU-02          ONLINE      14%     36%     OK        58°C
WH-GPU-03          SUSPECT     --      --      --        --
WH-GPU-04          OFFLINE     --      --      STALE     --


Project: Arya                             4 / 4 Online

Device             State       CPU     RAM     GPU       Temp
----------------------------------------------------------------
ARYA-GPU-01        ONLINE      33%     54%     OK        62°C
...
```

The page supports:

* project grouping
* project filtering
* device search
* status filtering

without becoming a multi-page administrative system.

---

# 38. Device Detail Expansion

Expanding a device row may show:

```text
Device Name
Project
UUID
Hostname
IP
Operating System
Agent Version
Last Seen
Uptime

CPU

Memory

Storage
    mount
    used
    total
    percent

GPU 0
    UUID
    model
    utilization
    temperature
    VRAM
    driver
    health

GPU 1
    ...

Recent Events
```

Offline values must be visibly marked:

```text
STALE
```

Unavailable values must display:

```text
N/A
```

not:

```text
0
```

unless zero is an actual measurement.

---

# 39. Database

Database:

```text
MySQL 8.x
```

Storage engine:

```text
InnoDB
```

Character set:

```text
utf8mb4
```

All schema modifications use Alembic migrations.

No manual production schema modifications are considered authoritative.

---

# 40. Logical Database Schema

The initial logical schema is:

```text
projects
    │
    └── devices
          │
          ├── device_credentials
          ├── heartbeat_receipts
          ├── heartbeat_samples
          ├── device_latest
          ├── incidents
          │      └── alert_events
          │              └── notification_deliveries
          │                       └── notification_attempts
          │
          └── audit_events

admin_sessions
oauth_transactions
```

Additional operational tables may be introduced only when required by an approved implementation stage.

---

# 41. projects

Suggested fields:

```text
id                  BIGINT UNSIGNED
public_id           CHAR(36)
name                VARCHAR(128)
description         VARCHAR(512) NULL
is_active           BOOLEAN
created_at          DATETIME(6)
updated_at          DATETIME(6)
```

Constraints/indexes:

```text
PRIMARY KEY(id)

UNIQUE(public_id)

INDEX(name)

INDEX(is_active)
```

`public_id` may be UUID-based and provides an externally safe project identifier if one is required.

Internal joins may use numeric IDs for straightforward MySQL indexing.

---

# 42. devices

Suggested fields:

```text
id                       BIGINT UNSIGNED
device_uuid              CHAR(36)
project_id               BIGINT UNSIGNED

name                     VARCHAR(128)

monitoring_enabled       BOOLEAN
monitoring_started_at    DATETIME(6)

availability_state       VARCHAR(32)
last_seen_at             DATETIME(6) NULL

gpu_monitoring_enabled   BOOLEAN
expected_gpu_min_count   SMALLINT UNSIGNED
expected_gpu_uuids       JSON NULL

gpu_effective_state      VARCHAR(32)
gpu_failure_streak       SMALLINT UNSIGNED
gpu_ok_streak            SMALLINT UNSIGNED
gpu_last_sample_at       DATETIME(6) NULL

created_at               DATETIME(6)
updated_at               DATETIME(6)
```

Constraints/indexes:

```text
PRIMARY KEY(id)

UNIQUE(device_uuid)

FOREIGN KEY(project_id)
    REFERENCES projects(id)

INDEX(project_id)

INDEX(project_id, monitoring_enabled)

INDEX(availability_state)

INDEX(last_seen_at)

INDEX(monitoring_enabled, last_seen_at)
```

The server should not depend on device name uniqueness across the whole platform.

Optionally enforce:

```text
UNIQUE(project_id, name)
```

if operators want unique names within each project.

---

# 43. device_credentials

Suggested fields:

```text
id
device_id
credential_id
secret_hash
created_at
expires_at
revoked_at
last_used_at
```

Important rules:

* raw secrets never stored
* credential belongs to exactly one device
* revoked credential cannot authenticate
* credential lookup is indexed
* rotation is audited

---

# 44. heartbeat_receipts

Purpose:

Short-lived idempotency records.

Fields:

```text
device_id
heartbeat_id
payload_hash
received_at
expires_at
response_payload
```

Primary/unique identity:

```text
(device_id, heartbeat_id)
```

Retention:

approximately 24 hours.

Expired records are removed in bounded batches.

---

# 45. heartbeat_samples

Purpose:

Historical raw/near-raw telemetry.

Suggested fields:

```text
id
device_id
heartbeat_id
received_at
collected_at
schema_version
agent_version
payload JSON
```

Indexes:

```text
(device_id, received_at)

received_at
```

The JSON payload is bounded by the API contract.

V1 does not provide arbitrary JSON metric queries.

---

# 46. device_latest

Purpose:

Fast dashboard access to the latest committed device observation.

Suggested fields:

```text
device_id
heartbeat_id
received_at
collected_at
schema_version
agent_version

hostname
primary_ip

cpu_percent
memory_percent
disk_summary

gpu_summary

payload JSON
```

Frequently displayed values may be represented as normal columns where this materially simplifies dashboard queries.

The complete latest telemetry payload may also remain in JSON.

There is exactly one latest row per device.

---

# 47. Why Keep Latest Separately?

Without `device_latest`, the dashboard would repeatedly need to locate:

```text
MAX(received_at)
```

for every device.

Instead:

```text
devices
JOIN device_latest
```

provides current status efficiently.

Historical retention can delete old heartbeat samples without affecting the latest dashboard snapshot.

---

# 48. Incidents

Suggested fields:

```text
id
incident_uuid
device_id
type

opened_at
detected_at

closed_at NULL
close_reason NULL

created_at
updated_at
```

Types initially include:

```text
AVAILABILITY

GPU
```

Only one active incident of the same type should exist for a device.

This must be enforced using a MySQL-compatible transactional/constraint design.

---

# 49. alert_events

Suggested fields:

```text
id
event_uuid
incident_id
kind
occurred_at
created_at
metadata JSON
```

Example kinds:

```text
DEVICE_OFFLINE

DEVICE_RECOVERED

GPU_DEGRADED

GPU_RECOVERED
```

Event creation is durable.

An event may exist even when no notification channel is configured.

---

# 50. notification_deliveries

Suggested fields:

```text
id
delivery_uuid

event_id

channel
recipient_key
recipient_address

provider_name

status
attempt_count

next_attempt_at
expires_at

lease_token
lease_expires_at

superseded_at

last_error_category
provider_message_id

cancel_reason

created_at
updated_at
```

Unique logical delivery:

```text
event
+
channel
+
recipient
```

Indexes should support efficiently finding:

```text
PENDING / RETRY_WAIT
```

deliveries whose:

```text
next_attempt_at <= NOW()
```

---

# 51. notification_attempts

Suggested fields:

```text
id
delivery_id
attempt_no

started_at
finished_at

outcome

error_category
provider_message_id
```

Do not store:

* SMTP passwords
* SMS tokens
* authorization headers
* full sensitive provider responses

---

# 52. admin_sessions

Suggested fields:

```text
id
session_hash

google_sub
email
hosted_domain

issued_at
expires_at
last_used_at
revoked_at

authorization_policy_version
```

Raw browser session tokens are never stored.

---

# 53. oauth_transactions

Short-lived table used during Google OIDC flow.

May contain:

```text
state_hash
nonce_hash
browser_binding_hash
PKCE-related protected data
expires_at
consumed_at
```

Transactions are:

* short-lived
* single-use
* removed after expiry

---

# 54. audit_events

Administrative changes should generate audit events.

Examples:

```text
PROJECT_CREATED

PROJECT_UPDATED

DEVICE_ENROLLED

DEVICE_RENAMED

DEVICE_PROJECT_CHANGED

DEVICE_DISABLED

DEVICE_ENABLED

CREDENTIAL_CREATED

CREDENTIAL_REVOKED

CREDENTIAL_ROTATED

GPU_BASELINE_CHANGED
```

Suggested fields:

```text
id

actor_type
actor_identifier

action

project_id NULL
device_id NULL

occurred_at

safe_metadata JSON
```

Secrets must never appear in audit metadata.

---

# 55. Telemetry Storage Strategy

V1 deliberately uses a hybrid strategy.

Historical heartbeat:

```text
bounded JSON payload
```

Latest status:

```text
selected query-friendly columns
+
bounded JSON payload
```

This avoids prematurely creating dozens of metric tables.

The architecture does NOT currently provide:

* arbitrary telemetry query language
* long-term analytics engine
* Prometheus replacement
* time-series database

If long-term graphing becomes important later, telemetry storage may be evolved separately.

---

# 56. Retention

Initial proposed retention:

```text
Heartbeat samples:
7 days

Heartbeat deduplication receipts:
24 hours

Closed incidents:
90 days

Alert events:
90 days

Notification history:
90 days

Audit history:
90 days minimum
```

Latest device state remains while the device remains registered.

Open incidents and active notification jobs must not be deleted by routine retention.

Retention cleanup operates in bounded batches to avoid long database locks.

Retention values remain configurable.

---

# 57. Capacity Estimate

At:

```text
100 devices
30-second heartbeat
```

expected heartbeat volume is approximately:

```text
3.33 / second

288,000 / day

2,016,000 / 7 days
```

Actual disk consumption depends heavily on heartbeat payload size.

If the average stored heartbeat is approximately 8 KiB, raw payload storage alone can exceed:

```text
15 GiB / seven days
```

before considering:

* indexes
* MySQL row overhead
* binary logs
* notification history
* backups
* filesystem free-space margin

Production sizing must therefore be based on measured payload sizes.

---

# 58. Initial VM Sizing

Starting test assumption:

```text
2–4 vCPU

4–8 GB RAM

80+ GB storage
```

This is NOT a production guarantee.

Load/soak testing determines final sizing.

Storage should be increased if:

* heartbeat retention increases
* payload size increases
* device count increases
* binary-log retention increases

---

# 59. Database Backup

MySQL persistent Docker storage is NOT itself a backup.

Production requires:

* scheduled backup
* off-host storage
* encryption
* retention policy
* restoration testing

Initial proposal:

```text
daily backup
```

with approximately:

```text
RPO <= 24 hours
```

The actual RPO/RTO must be approved before production deployment.

A backup is not considered operational until restoration has been successfully tested.

---

# 60. Monitoring Server Blind Spot

If the central VM itself fails:

* heartbeats cannot be received
* outages cannot be evaluated normally
* notifications cannot be sent

Therefore the monitoring server needs an independent external uptime check.

That external checker is outside this application's V1 implementation.

---

# 61. Agent Architecture

The edge agent remains intentionally small.

```text
skybeat-agent
│
├── config
├── scheduler/runtime
├── system collector
├── filesystem collector
├── GPU collector
├── telemetry builder
└── HTTP transport
```

No inbound listener is required.

The agent only initiates outbound HTTPS connections.

---

# 62. Agent Failure Isolation

Collectors should fail independently.

Example:

```text
CPU       OK
RAM       OK
Disk      OK
GPU       NVIDIA_SMI_FAILED
```

must still produce a heartbeat.

A GPU failure must not prevent CPU/system telemetry from reaching the server.

---

# 63. Agent Queue Behavior

V1 does not maintain an unlimited offline telemetry queue.

If networking is unavailable:

```text
sample A fails
sample B generated later
```

the agent may prioritize the newest current sample instead of indefinitely storing every old observation.

Availability is determined from server receipt times, so replaying a large old queue provides little value for current health determination.

---

# 64. Agent Subprocess Safety

`nvidia-smi` execution must have:

* explicit timeout
* bounded stdout
* bounded stderr
* controlled process cleanup

A hanging `nvidia-smi` must not hang the monitoring agent indefinitely.

The GPU collector converts failures into explicit telemetry states.

---

# 65. systemd

The agent runs as:

```text
skybeat-agent.service
```

Requirements:

* starts after networking
* starts on boot
* restarts after crash
* sensible restart delay
* graceful SIGTERM
* dedicated configuration file
* least-privilege service identity where practical

Example configuration location:

```text
/etc/skybeat-agent/agent.env
```

with restrictive permissions.

---

# 66. Docker Deployment

Central VM:

```text
Docker Compose
│
├── caddy
├── api
├── worker
└── mysql
```

Conceptually:

```text
Internet
   │
   ▼
Caddy
   │
   ▼
API
   │
   ▼
MySQL
   ▲
   │
Worker
```

MySQL exists only on the internal application network.

---

# 67. Secrets

Production secrets must be supplied outside Git.

Examples:

```text
MYSQL_PASSWORD

DEVICE credential material

GOOGLE_CLIENT_SECRET

SESSION_SECRET / encryption keys

SMTP_PASSWORD

SMS_API_KEY
```

`.env.example` contains variable names and safe examples only.

Real `.env` files must be excluded from Git.

---

# 68. Repository Structure

```text
skybeat/
│
├── AGENTS.md
├── README.md
├── .gitignore
├── .env.example
├── docker-compose.yml
│
├── server/
│   │
│   ├── pyproject.toml
│   ├── requirements.lock
│   ├── alembic.ini
│   │
│   ├── migrations/
│   │   └── versions/
│   │
│   ├── app/
│   │   │
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── db.py
│   │   ├── cli.py
│   │   │
│   │   ├── api/
│   │   │
│   │   ├── models/
│   │   │
│   │   ├── schemas/
│   │   │
│   │   ├── projects/
│   │   │
│   │   ├── devices/
│   │   │
│   │   ├── heartbeats/
│   │   │
│   │   ├── health/
│   │   │
│   │   ├── alerts/
│   │   │
│   │   ├── notifications/
│   │   │
│   │   ├── auth/
│   │   │
│   │   └── workers/
│   │
│   └── tests/
│
├── agent/
│   │
│   ├── pyproject.toml
│   ├── requirements.lock
│   │
│   ├── src/
│   │   └── skybeat_agent/
│   │       ├── main.py
│   │       ├── config.py
│   │       ├── runtime.py
│   │       ├── telemetry.py
│   │       ├── transport.py
│   │       │
│   │       └── collectors/
│   │           ├── system.py
│   │           ├── filesystem.py
│   │           └── gpu.py
│   │
│   └── tests/
│
├── web/
│   ├── templates/
│   │   └── device_status.html
│   │
│   └── static/
│       ├── css/
│       └── js/
│
├── deployment/
│   │
│   ├── docker/
│   │   └── Dockerfile.server
│   │
│   ├── caddy/
│   │   └── Caddyfile
│   │
│   └── systemd/
│       ├── skybeat-agent.service
│       └── agent.env.example
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── REQUIREMENTS.md
│   ├── SECURITY.md
│   ├── DEPLOYMENT.md
│   ├── API_SPEC.md
│   ├── AGENT_SPEC.md
│   ├── ALERTING.md
│   └── IMPLEMENTATION_PLAN.md
│
├── tests/
│   ├── contracts/
│   ├── integration/
│   ├── failure/
│   └── load/
│
└── scripts/
```

---

# 69. Module Responsibilities

## projects/

Responsible for:

* project creation
* project updates
* project status
* device assignment
* project queries

---

## devices/

Responsible for:

* device enrollment
* device naming
* device policy
* credential lifecycle
* GPU expected inventory
* monitoring enable/disable

---

## heartbeats/

Responsible for:

* heartbeat authentication integration
* idempotency
* ingestion
* telemetry persistence
* latest snapshot updates

---

## health/

Responsible for pure/testable:

* availability transition calculations
* GPU transition calculations
* threshold evaluation

Avoid HTTP/database concerns inside pure transition functions.

---

## alerts/

Responsible for:

* incidents
* alert events
* recovery events
* recipient snapshot/materialization rules

---

## notifications/

Responsible for:

* delivery state
* retries
* SMTP adapter
* SMS adapter interface
* provider error classification

---

## auth/

Responsible for:

* Google OIDC
* allowlist authorization
* sessions
* logout
* OAuth transaction state

---

## workers/

Responsible for:

* availability sweep
* alert materialization
* notification delivery
* retention cleanup
* worker health

---

# 70. API / Service / Repository Separation

Preferred call structure:

```text
API route
    ↓
Service
    ↓
Repository
    ↓
SQLAlchemy
    ↓
MySQL
```

Routes should not contain large amounts of business logic.

ORM models should not be reused directly as API schemas.

Pydantic models and persistence models remain separate.

---

# 71. Concurrency Rules

When modifying device health state:

1. begin transaction
2. lock device row
3. re-read state
4. calculate transition
5. modify incident/event state
6. update device
7. commit

Use a consistent lock ordering.

Never:

```text
lock device
→ call SMTP
```

or:

```text
lock device
→ call SMS
```

Provider communication happens independently through delivery jobs.

---

# 72. MySQL-Specific Design Rule

Do not copy PostgreSQL-specific SQL patterns into the implementation.

In particular, review alternatives for:

* partial unique indexes
* `JSONB`
* `timestamptz`
* PostgreSQL-specific enum behavior
* PostgreSQL advisory locks
* PostgreSQL-specific `RETURNING`
* PostgreSQL time functions

Use MySQL 8.x-compatible:

* JSON
* DATETIME(6)/appropriate UTC handling
* InnoDB transactions
* generated columns where justified
* normal/composite unique indexes
* `SELECT ... FOR UPDATE`
* migration-managed constraints

Every concurrency-sensitive behavior must be tested against real MySQL 8.x.

---

# 73. Error Handling

Expected failures should return safe structured errors.

Unexpected failures:

* are logged
* include request correlation where appropriate
* do not expose stack traces to clients
* do not expose credentials
* fail safely

Heartbeat failures must distinguish where practical:

```text
authentication failure

validation failure

rate/size rejection

database unavailable

conflict
```

---

# 74. Logging

Structured logs should include:

```text
timestamp
level
component
request_id
device_uuid when relevant
event category
safe error category
```

Never log:

```text
device secret
Authorization header
Google token
session token
SMTP password
SMS API key
database password
```

Logs require production rotation and retention.

---

# 75. Health Endpoints

Server should expose:

```text
/livez
```

for basic process liveness.

And:

```text
/readyz
```

for readiness.

Readiness may depend on critical resources such as MySQL connectivity.

Health endpoints must not expose sensitive system configuration.

---

# 76. Production Failure Boundaries

Expected failure handling:

## MySQL unavailable

API must not acknowledge uncommitted heartbeats.

Readiness fails.

---

## SMTP unavailable

Heartbeats continue.

Notification becomes retryable/failed according to policy.

---

## SMS unavailable

Email may still proceed.

Heartbeat processing continues.

---

## Google unavailable

Existing valid application sessions may continue according to session policy.

New Google authentication may temporarily fail.

Agent heartbeats are unaffected.

---

## Worker unavailable

Heartbeats continue to be persisted.

Availability/notification processing may be delayed.

Worker health must therefore be observable.

---

## API unavailable

Agents retry using bounded backoff.

No infinite local backlog is created.

---

# 77. Production Acceptance Architecture Tests

Before V1 is considered production-ready, test:

* 100 simulated devices
* 30-second heartbeat pattern
* concurrent heartbeat requests
* duplicate heartbeat
* malformed heartbeat
* device credential revocation
* credential rotation
* device reassignment between projects
* agent killed
* device reboot
* network disconnected
* API restarted
* worker restarted
* MySQL restarted
* monitoring VM restarted
* nvidia-smi timeout
* NVIDIA driver failure
* GPU disappearance
* multiple GPU reorder
* SMTP outage
* SMS outage
* Google authorization rejection
* stale dashboard telemetry
* database backup restoration

---

# 78. Architectural Decisions Locked for V1

The following are the baseline V1 architecture:

```text
Database
    MySQL 8.x

Server
    FastAPI

Architecture
    Modular monolith

Background processing
    Separate worker process

Reverse proxy
    Caddy

Frontend
    Jinja2 + small JavaScript

Agent
    Python + systemd

Authentication
    Google OIDC

Device authentication
    Per-device credential

Device organization
    Project → Devices

Availability authority
    Central server

Heartbeat interval
    approximately 30 seconds

Initial fleet
    up to 100 devices

Notifications
    SMTP + replaceable SMS adapter
```

---

# 79. Deliberately Deferred Architecture

V1 intentionally does not include:

```text
Redis
Celery
Kafka
RabbitMQ
Kubernetes
microservices
time-series database
React/Vue frontend
WebSockets
remote commands
remote reboot
remote shell
self-healing
automatic remediation
```

These may be reconsidered only when a demonstrated requirement justifies the additional complexity.

---

# 80. Cross-Document Ownership

`REQUIREMENTS.md`

owns:

* product scope
* functional requirements
* acceptance criteria

`ARCHITECTURE.md`

owns:

* system structure
* component responsibilities
* persistence architecture
* architectural decisions

`API_SPEC.md`

owns:

* HTTP contracts
* heartbeat wire format
* API error contracts

`AGENT_SPEC.md`

owns:

* collection
* scheduling
* edge runtime behavior

`ALERTING.md`

owns:

* state transitions
* incident lifecycle
* notification lifecycle

`SECURITY.md`

owns:

* threat model
* authentication
* authorization
* credential handling
* trust boundaries

`DEPLOYMENT.md`

owns:

* Docker deployment
* VM setup
* configuration
* TLS
* backup/restore
* operational procedures

`IMPLEMENTATION_PLAN.md`

owns:

* development stages
* stage acceptance
* implementation order

If documents conflict, implementation must stop until the conflict is resolved.

---

# 81. Implementation Principle

Architecture should remain intentionally simple.

For every proposed new infrastructure component ask:

```text
What current production requirement requires this?
```

If there is no concrete answer, do not add it.

V1's objective is not to build a general-purpose observability platform.

The objective is to reliably answer:

```text
Which project is this device assigned to?

Is the device contacting us?

When did we last see it?

What are its current CPU/RAM/storage conditions?

Are its NVIDIA GPUs visible and healthy?

Did something go offline?

Did it recover?

Were administrators notified?
```

If V1 answers those questions reliably, securely, and operationally, the architecture has achieved its purpose.
