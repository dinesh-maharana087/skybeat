# SkyBeat V1 Implementation Plan

Status: approved V1 implementation roadmap.

## Goal

Build and deploy a standalone monitoring and alerting platform for approximately 100 Linux/GPU devices using one Ubuntu VM.

The target is a functional production-oriented V1 within approximately 2–3 focused implementation days.

The system provides:

* Linux device monitoring
* CPU telemetry
* memory telemetry
* storage telemetry
* uptime
* NVIDIA GPU telemetry
* centralized availability detection
* Project → Device organization
* OFFLINE and RECOVERED incidents
* email notifications
* replaceable SMS notification interface
* Google-authenticated dashboard
* one Device Status page
* persistent history
* secure per-device authentication

V1 does NOT provide:

* remote shell
* arbitrary commands
* reboot
* service restart
* OS modification
* driver modification
* repair
* self-healing

---

# 1. Approved Architecture

```text
Linux / GPU Agents
        │
        │ HTTPS heartbeat
        ▼
      Caddy
        │
        ▼
     FastAPI
        │
        ▼
    MySQL 8.x
        ▲
        │
      Worker
        │
        ├── SMTP
        └── SMS Provider
```

Browser:

```text
Browser
   │
   │ HTTPS
   ▼
 Caddy
   │
   ▼
FastAPI
   │
   ├── Google OIDC
   └── Jinja2 Device Status page
```

---

# 2. Technology Stack

Central server:

```text
Ubuntu 24.04 LTS

Python 3.12

FastAPI

Pydantic 2

SQLAlchemy 2

Alembic

MySQL 8.x

InnoDB

Uvicorn

Jinja2

Caddy

Docker Compose
```

Agent:

```text
Python 3.12 where available

psutil

HTTP client

nvidia-smi

systemd
```

Testing/tooling:

```text
pytest

ruff

mypy where practical

real MySQL 8.x integration tests
```

Exact dependency versions must be pinned during implementation.

---

# 3. Authoritative Specifications

Implementation must follow:

```text
docs/REQUIREMENTS.md

docs/ARCHITECTURE.md

docs/API_SPEC.md

docs/AGENT_SPEC.md

docs/ALERTING.md

docs/SECURITY.md

docs/DEPLOYMENT.md

docs/IMPLEMENTATION_PLAN.md
```

And repository-level:

```text
AGENTS.md
```

If implementation discovers a contradiction between approved specifications:

```text
STOP
   ↓
identify conflict
   ↓
propose smallest correction
   ↓
obtain approval when architectural/security behavior changes
```

Do not silently invent a new architecture.

---

# 4. Implementation Philosophy

The project must be built vertically.

Prefer:

```text
working end-to-end path
```

over:

```text
many unfinished subsystems
```

First prove:

```text
Agent
  ↓
Heartbeat
  ↓
FastAPI
  ↓
MySQL
```

Then:

```text
Heartbeat missing
  ↓
OFFLINE
  ↓
Incident
  ↓
Email
```

Then:

```text
Heartbeat returns
  ↓
RECOVERED
  ↓
Recovery Email
```

Then:

```text
Dashboard
+
Google Auth
+
GPU health
+
SMS boundary
+
hardening
```

---

# 5. Global Constraints

The following are locked for V1.

Standalone project:

```text
No Canopus dependency.
```

Capacity:

```text
approximately 100 devices
```

Heartbeat:

```text
approximately 30 seconds
with small jitter
```

Availability:

```text
ONLINE:
age < 75 sec

SUSPECT:
75 <= age < 180 sec

OFFLINE:
age >= 180 sec
```

Health sweep:

```text
approximately 5 sec
```

Authoritative availability time:

```text
central server receipt time
```

Database:

```text
MySQL 8.x
InnoDB
utf8mb4
UTC
```

Public transport:

```text
HTTPS only
```

Agent:

```text
outbound communication only
```

No inbound agent listener.

No remote-control functionality.

---

# 6. Device Identity

Each device has:

```text
Project

Device UUID

Device Name

Hostname

Credential
```

These are separate concepts.

Device UUID:

```text
immutable technical identity
```

Device Name:

```text
human-friendly operator label
```

Hostname:

```text
reported Linux hostname
```

Project:

```text
server-controlled organizational assignment
```

Renaming or moving a device must not change:

* UUID
* credential
* telemetry history
* incident history

---

# 7. Execution Model

For each implementation stage:

1. Read the relevant approved specifications.
2. Inspect existing repository code.
3. Implement only the scoped functionality.
4. Add tests for important behavior and failure cases.
5. Run relevant tests.
6. Run formatting/static checks.
7. Inspect the resulting diff.
8. Report files changed.
9. Report commands executed.
10. Report exact test results.
11. Report unresolved issues.
12. Stop at the stage boundary when review is requested.

Do not implement unrelated future functionality merely because the architecture mentions it.

---

# 8. Stage 00 — Documentation

Status:

```text
COMPLETE
```

Documents:

```text
REQUIREMENTS.md

ARCHITECTURE.md

API_SPEC.md

AGENT_SPEC.md

ALERTING.md

SECURITY.md

DEPLOYMENT.md

IMPLEMENTATION_PLAN.md
```

Final remaining documentation task:

```text
AGENTS.md consistency review
```

No application implementation belongs to Stage 00.

---

# 9. Stage 01 — Foundation + Database + Device Identity

## Objective

Establish the complete server foundation required for heartbeat ingestion.

This stage combines the original foundation and enrollment work because separating them provides little value for the short V1 schedule.

## Create

Conceptual structure:

```text
server/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── logging.py
│   ├── db.py
│   ├── api/
│   │   └── health.py
│   ├── devices/
│   ├── models/
│   └── cli.py
├── migrations/
├── tests/
├── pyproject.toml
└── requirements.lock
```

Root:

```text
.gitignore

.env.example

README.md
```

## Implement

* FastAPI application factory
* typed settings
* safe structured logging
* MySQL SQLAlchemy engine
* session/transaction helper
* Alembic
* `/livez`
* `/readyz`
* Project model
* Device model
* Device credential model
* audit model
* local enrollment CLI
* credential rotation
* credential revocation
* device enable/disable
* project assignment
* expected GPU policy

## Initial schema

At minimum:

```text
projects

devices

device_credentials

audit_events
```

## Credential behavior

Credential format:

```text
sb1.<credential_id>.<secret>
```

Secret:

```text
>=256 bits random
```

Server stores:

```text
credential identifier

device binding

secure digest

created_at

expires_at

revoked_at
```

Never store the raw secret.

## Tests

Test:

* MySQL connectivity
* migration upgrade
* invalid configuration
* readiness without DB
* enrollment
* unique UUID
* credential generation
* hash-only persistence
* credential/device binding
* revocation
* rotation
* device disable
* project assignment
* audit trail
* secret redaction

## Acceptance

A local operator can:

```text
create project
     ↓
enroll device
     ↓
receive UUID + credential
```

and MySQL retains the identity across restart.

No heartbeat endpoint yet.

---

# 10. Stage 02 — Heartbeat API + Agent

## Objective

Get a real Linux device reporting telemetry into MySQL.

This is the most important implementation milestone.

## Server work

Implement:

```text
POST /api/v1/heartbeats
```

Create approximately:

```text
server/app/api/heartbeats.py

server/app/schemas/heartbeat.py

server/app/heartbeats/service.py

server/app/heartbeats/repository.py

server/app/models/heartbeat.py
```

Database additions:

```text
heartbeat_receipts

heartbeat_samples

device_latest
```

## Heartbeat authentication

Verify:

```text
Bearer token

credential active

credential belongs to device

device enabled
```

Reject identity mismatch.

---

# 11. Heartbeat Validation

Implement the exact contract from `API_SPEC.md`.

Enforce:

```text
schema_version

heartbeat_id

device_id

agent_version

collected_at

hostname

ip_addresses

os

uptime

CPU

memory

disks

GPU health

GPU inventory
```

Maximum:

```text
request body:
128 KiB

IP addresses:
16

disks:
64

GPUs:
64
```

Reject malformed/unsupported payloads.

---

# 12. Heartbeat Idempotency

Logical key:

```text
device_id + heartbeat_id
```

Retention:

```text
at least 24 hours
```

First valid request:

```text
persist
   ↓
update latest
   ↓
return acknowledgement
```

Identical retry:

```text
return original acknowledgement
```

Do NOT:

```text
refresh last_seen

advance GPU confirmation

update latest telemetry

create events
```

Same heartbeat ID with different payload:

```text
409 heartbeat_id_conflict
```

---

# 13. Agent Implementation

Create:

```text
agent/
├── src/
│   └── skybeat_agent/
│       ├── main.py
│       ├── config.py
│       ├── runtime.py
│       ├── telemetry.py
│       ├── transport.py
│       └── collectors/
│           ├── system.py
│           ├── filesystems.py
│           ├── gpu.py
│           └── subprocess_runner.py
├── tests/
├── pyproject.toml
└── requirements.lock
```

Configuration:

```text
SERVER_URL

DEVICE_UUID

DEVICE_TOKEN
```

plus safe optional tuning.

Agent does NOT require:

```text
project ID

project name

device name
```

---

# 14. System Telemetry

Collect:

```text
hostname

IP addresses

OS

kernel

architecture

uptime

CPU utilization

memory

filesystems
```

Collector failure must not crash the entire agent.

Unavailable metrics become:

```text
null
```

where defined by the API contract.

---

# 15. GPU Telemetry

Use:

```text
/usr/bin/nvidia-smi
```

where available.

Requirements:

```text
shell=False

fixed arguments

read-only query

timeout approximately 5 sec

bounded stdout/stderr

bounded child processes
```

Support multiple physical GPUs.

Prefer:

```text
GPU UUID
```

over GPU index as persistent identity.

States:

```text
OK

GPU_MISSING

NVIDIA_SMI_FAILED

DRIVER_ERROR

UNKNOWN
```

Reason codes must follow the finite vocabulary in `AGENT_SPEC.md`.

---

# 16. Agent Transport

Normal interval:

```text
30 seconds
```

with small jitter.

Each new telemetry snapshot receives a new:

```text
heartbeat_id
```

Retries of the same snapshot reuse:

```text
same heartbeat_id

same payload
```

Total attempt deadline:

```text
approximately 10 seconds
```

No TLS verification bypass.

No unlimited offline queue.

Fresh telemetry may supersede old unsent routine telemetry.

---

# 17. Stage 02 Tests

Server:

* authentication
* revoked credential
* identity mismatch
* malformed JSON
* schema validation
* payload size
* duplicate heartbeat
* heartbeat conflict
* MySQL rollback
* concurrent duplicate request

Agent:

* CPU collection
* memory collection
* filesystem failure
* IP bounds
* GPU missing
* `nvidia-smi` timeout
* driver failure
* multiple GPUs
* malformed GPU output
* TLS/network failure
* retry
* graceful stop
* no secret logging

Integration:

```text
real agent
   ↓
real FastAPI
   ↓
real MySQL
```

## Acceptance

A Linux/GPU device sends a real heartbeat and MySQL contains:

```text
device identity

latest telemetry

heartbeat history

GPU telemetry
```

This is the **Day-1 functional milestone**.

---

# 18. Stage 03 — Availability + Incidents + Email

## Objective

Turn heartbeat data into an operational monitoring system.

Implement:

```text
ONLINE

SUSPECT

OFFLINE
```

and:

```text
DEVICE_OFFLINE

DEVICE_RECOVERED
```

---

# 19. Health Worker

Create approximately:

```text
server/app/health/

server/app/alerts/

server/app/workers/
```

Worker responsibilities:

```text
availability sweep

GPU evaluation

incident/event persistence

notification processing

retention later
```

Initial availability sweep:

```text
5 seconds
```

---

# 20. Availability Logic

Use:

```text
server receipt timestamp
```

not:

```text
agent collected_at
```

Thresholds:

```text
<75 sec
ONLINE

75–<180 sec
SUSPECT

>=180 sec
OFFLINE
```

---

# 21. Late Heartbeat Rule

A heartbeat arriving after the OFFLINE threshold must not erase the outage simply because the worker sweep was delayed.

Example:

```text
last heartbeat:
12:00:00

offline threshold:
12:03:00

new heartbeat:
12:03:10
```

Persist logically:

```text
OFFLINE
   ↓
RECOVERED
```

The heartbeat transaction and health sweep use the same device-row serialization strategy.

---

# 22. MySQL Concurrency

Use MySQL 8.x/InnoDB row locking.

Conceptually:

```sql
SELECT ...
FROM devices
WHERE id = ?
FOR UPDATE;
```

Test concurrency against real MySQL.

Do not use SQLite to validate locking behavior.

---

# 23. Incidents

Add:

```text
incidents

alert_events
```

One continuing availability outage:

```text
one incident

one DEVICE_OFFLINE event
```

Recovery:

```text
close incident

one DEVICE_RECOVERED event
```

New outage:

```text
new incident
```

---

# 24. Notification Persistence

Add:

```text
notification_deliveries

notification_attempts
```

Initial delivery states:

```text
PENDING

IN_PROGRESS

RETRY_WAIT

SUCCEEDED

FAILED

CANCELLED
```

Events and initial delivery jobs must be committed durably before provider communication.

---

# 25. Email Provider

Implement SMTP first.

Email events:

```text
DEVICE_OFFLINE

DEVICE_RECOVERED
```

Initial delivery:

```text
maximum attempts:
5

provider timeout:
15 sec

notification expiry:
24 hours
```

Retry uses bounded exponential backoff with jitter.

SMTP failure must not affect heartbeat processing.

---

# 26. Recovery Supersession

When a device recovers:

```text
PENDING

RETRY_WAIT
```

offline notifications for that incident should be cancelled.

Reason:

```text
superseded_by_recovery
```

Already in-flight external delivery cannot always be recalled.

---

# 27. Stage 03 Tests

Availability boundaries:

```text
74.999

75

179.999

180
```

Also:

* first heartbeat
* never-seen device
* first contact after OFFLINE
* repeated sweeps
* duplicate heartbeat
* heartbeat/sweep race
* late heartbeat
* second outage
* restart
* MySQL rollback

Notification:

* one outage → one alert
* recovery → one recovery
* SMTP timeout
* temporary SMTP failure
* permanent failure
* retry
* recovery cancellation
* worker restart
* provider failure does not block heartbeat

## Acceptance

This exact flow must work:

```text
Device active
   ↓
ONLINE

stop agent
   ↓
SUSPECT
   ↓
OFFLINE
   ↓
incident
   ↓
email
```

Then:

```text
start agent
   ↓
heartbeat
   ↓
ONLINE
   ↓
incident closes
   ↓
RECOVERED email
```

This is the **Day-2 critical milestone**.

---

# 28. Stage 04 — Dashboard + Google Authentication

## Objective

Provide one secure operational status page.

Implement Google OIDC authentication and explicit authorization.

---

# 29. Authentication

Implement:

```text
/auth/google/login

/auth/google/callback

POST /auth/logout
```

Use:

```text
authorization-code flow

state

nonce

PKCE where supported
```

Validate:

```text
signature

issuer

audience

expiry

verified email
```

---

# 30. Authorization

Support:

```text
explicit email allowlist
```

Optional:

```text
approved Google Workspace domain
```

Empty authorization configuration:

```text
DENY
```

not:

```text
ALLOW ALL
```

---

# 31. Sessions

Use application-owned opaque sessions.

Store only session digest in MySQL.

Recommended:

```text
absolute lifetime:
8 hours

idle:
30 minutes
```

Cookie:

```text
Secure

HttpOnly

SameSite=Lax

Path=/
```

---

# 32. Dashboard API

Implement:

```text
GET /api/v1/projects

GET /api/v1/devices

GET /api/v1/devices/{device_uuid}

GET /api/v1/devices/{device_uuid}/alerts
```

All require dashboard authorization.

---

# 33. Device Status Page

One main page.

Display:

```text
Project

Device Name

Hostname

Availability

Last Seen

CPU

RAM

Disk

GPU

GPU health

Agent version
```

Allow expansion/detail for:

```text
multiple disks

multiple GPUs

incident history

notification status
```

---

# 34. Dashboard Freshness

Poll approximately:

```text
15 seconds
```

No WebSocket infrastructure is required.

Offline telemetry must be marked:

```text
STALE
```

Never present stale CPU/GPU values as current.

---

# 35. Stage 04 Tests

Test:

* authorized Google user
* unauthorized Google user
* empty allowlist
* expired session
* logout
* allowlist removal
* protected API
* hostile device name
* XSS payload
* no devices
* awaiting first heartbeat
* ONLINE
* SUSPECT
* OFFLINE
* stale telemetry
* multiple disks
* multiple GPUs
* null values
* dashboard polling failure

## Acceptance

Authorized user can securely view:

```text
Project
  ↓
Devices
  ↓
Current status
  ↓
Telemetry
  ↓
Incidents
```

Unauthorized users cannot obtain operational data.

---

# 36. Stage 05 — GPU Incidents + SMS Boundary

## Objective

Complete the remaining V1 alerting capabilities.

---

# 37. GPU Effective Health

Server evaluates agent observations against server policy:

```text
gpu_monitoring_enabled

expected_gpu_min_count

expected_gpu_uuids
```

Agent cannot change these values.

CPU-only device:

```text
GPU monitoring:
NOT MONITORED
```

---

# 38. GPU Confirmation

Degradation:

```text
2 consecutive fresh non-OK samples
```

Recovery:

```text
2 consecutive fresh OK samples
```

Maximum confirmation gap:

```text
75 seconds
```

Duplicate heartbeat retries do not count.

---

# 39. GPU Events

Implement:

```text
GPU_DEGRADED

GPU_RECOVERED
```

Availability and GPU health remain independent.

Example:

```text
Device:
ONLINE

GPU:
DRIVER_ERROR
```

is valid.

---

# 40. Offline During GPU Incident

If device becomes OFFLINE:

* retain GPU incident history
* mark telemetry stale
* reset confirmation streaks
* do not make fresh GPU conclusions
* availability becomes the primary current condition

Device recovery does NOT automatically close GPU incident.

Require two fresh OK GPU samples.

---

# 41. SMS Provider Interface

Implement provider abstraction:

```text
NotificationProvider
```

with:

```text
EmailProvider

SMSProvider
```

Result categories:

```text
ACCEPTED

TRANSIENT_FAILURE

PERMANENT_FAILURE

UNCERTAIN
```

Core incident logic must not import vendor-specific SMS behavior.

---

# 42. SMS Production Scope

If the actual SMS provider is selected and credentials/approval are available:

```text
implement provider adapter
```

Otherwise:

```text
implement tested provider interface
+
fake/no-op adapter
+
document production SMS pending
```

Do not delay the entire V1 because an external SMS provider is unavailable.

---

# 43. Stage 05 Tests

GPU:

* one bad sample
* two bad samples
* continuing bad samples
* one good sample
* two good samples
* confirmation gap
* GPU missing
* driver failure
* `nvidia-smi` failure
* multiple GPUs
* GPU reorder
* CPU-only device
* device offline during GPU incident

SMS:

* provider success
* transient failure
* permanent failure
* timeout
* email independence
* stable delivery identity
* no secret leakage

## Acceptance

GPU health produces stable incidents without false alerts from a single sample.

SMS can be replaced without changing incident logic.

---

# 44. Stage 06 — Deployment + Production Hardening

## Objective

Turn the working application into a reproducible deployment.

Create:

```text
docker-compose.yml

deployment/docker/Dockerfile.server

deployment/caddy/Caddyfile

deployment/systemd/skybeat-agent.service

deployment/systemd/agent.env.example

scripts/
```

---

# 45. Docker Compose

Services:

```text
caddy

api

worker

mysql
```

API and worker use:

```text
same image

different entry points
```

Only Caddy exposes public application ports.

Do NOT expose:

```text
3306

8000
```

publicly.

---

# 46. Agent systemd

Install:

```text
/opt/skybeat-agent/

/etc/skybeat-agent/agent.env

/etc/systemd/system/skybeat-agent.service
```

Run using dedicated:

```text
skybeat
```

user where practical.

No sudo.

No Docker socket.

No inbound listener.

---

# 47. Production Secrets

Keep outside Git:

```text
MySQL password

Google client secret

SMTP credentials

SMS credentials

device tokens

session/OAuth secrets

backup credentials
```

Commit only:

```text
.env.example

agent.env.example
```

---

# 48. Retention

Initial:

```text
heartbeat samples:
7 days

heartbeat receipts:
24 hours minimum

incidents:
90 days

events:
90 days

notification history:
90 days

audit:
90 days minimum
```

Cleanup uses bounded batches.

---

# 49. Backup

Initial:

```text
daily MySQL backup

30-day retention

off-host copy
```

Initial targets:

```text
RPO <=24 hours

RTO <=4 hours
```

Restore must be tested.

---

# 50. Logging

Use structured logs.

Never log:

```text
Authorization header

device token

Google token

session cookie

MySQL password

SMTP password

SMS secret
```

Docker logs must rotate.

---

# 51. Production Failure Tests

Before handoff test:

```text
stop agent

kill agent

reboot monitored device

disconnect network

restart API

restart worker

restart MySQL

restart central VM

break SMTP

break SMS adapter

hang/fail nvidia-smi

simulate expected GPU missing
```

Verify:

```text
detection

incident

notification

recovery

dashboard
```

---

# 52. MySQL Integration Tests

Critical concurrency tests must run against:

```text
MySQL 8.x / InnoDB
```

Test:

* `SELECT ... FOR UPDATE`
* concurrent heartbeat/sweep
* duplicate heartbeat
* duplicate incident prevention
* notification queue claiming
* `SKIP LOCKED`
* transaction rollback
* connection loss
* lock timeout
* worker restart
* MySQL restart

Do not use SQLite as proof of MySQL concurrency behavior.

---

# 53. Load Validation

Simulate:

```text
100 devices

approximately 30-second heartbeat
```

Expected average:

```text
~3.33 heartbeat requests/sec
```

Verify:

* API latency
* heartbeat success
* MySQL latency
* connection pool
* worker sweep
* CPU
* memory
* disk growth
* no false OFFLINE transitions

---

# 54. Soak Test

Run representative deployment for:

```text
24 hours
```

where deployment timing permits.

Observe:

```text
API memory

worker memory

MySQL memory

agent memory

agent CPU

disk growth

database connections

heartbeat timing

notification backlog

container logs
```

No unbounded growth is acceptable.

A production handoff occurring before a complete 24-hour soak must explicitly record that limitation rather than pretending the soak completed.

---

# 55. Final Production Gate

Required:

```text
HTTPS works

MySQL private

FastAPI private

per-device credentials

credential revocation tested

Google login works

explicit authorization works

heartbeat works

CPU/RAM/disk works

GPU works

ONLINE/SUSPECT/OFFLINE works

OFFLINE email works

RECOVERED email works

provider failure isolated

dashboard works

agent starts after reboot

backup exists

restore tested

secrets absent from Git

logs redact secrets
```

---

# 56. Day 1 Target

Primary objective:

```text
Repository foundation
        ↓
MySQL
        ↓
Device enrollment
        ↓
FastAPI
        ↓
Heartbeat API
        ↓
Agent
        ↓
CPU/RAM/Disk/GPU
        ↓
MySQL
```

End-of-day evidence:

```text
one real Linux/GPU device visible in database
```

Do not spend Day 1 polishing dashboard CSS.

---

# 57. Day 2 Target

Primary objective:

```text
Availability engine
       ↓
Incidents
       ↓
OFFLINE
       ↓
Email
       ↓
RECOVERED
       ↓
Email
       ↓
Dashboard
       ↓
Google Auth
```

End-of-day evidence:

```text
stop agent
    ↓
receive OFFLINE email

restart agent
    ↓
receive RECOVERED email
```

and the dashboard reflects both transitions.

---

# 58. Day 3 Target

Primary objective:

```text
GPU incident confirmation

SMS provider boundary

Docker Compose

Caddy

systemd

backup

restore test

failure tests

security hardening
```

Then:

```text
production acceptance review
```

---

# 59. Schedule Protection

If implementation time becomes constrained, prioritize:

```text
P0

Heartbeat ingestion

Agent

System telemetry

GPU telemetry

Availability

OFFLINE incident

RECOVERED incident

Email alerts

Basic dashboard

Authentication

HTTPS

Database persistence

Backup
```

Next:

```text
P1

GPU alerts

SMS provider integration

advanced dashboard detail

additional operational hardening
```

Later:

```text
P2

advanced visualization

WebSockets

Prometheus/Grafana

distributed infrastructure

advanced notification routing
```

Never sacrifice:

```text
authentication

HTTPS

correct outage logic

durable database commits

secret protection
```

to save implementation time.

---

# 60. What Codex Must Not Do

Codex must not independently add:

```text
PostgreSQL

SQLite production storage

Redis

Celery

RabbitMQ

Kafka

Kubernetes

React

Vue

remote commands

reboot

SSH execution

repair workflows

self-healing
```

unless the architecture is explicitly revised.

---

# 61. No Premature Abstractions

Do not build generic frameworks for hypothetical future features.

Examples:

Do not build:

```text
generic command engine

workflow engine

plugin marketplace

distributed event bus

multi-region architecture

remote execution framework
```

V1 should remain a modular monolith.

---

# 62. Error Handling

All external operations must be bounded.

This includes:

```text
HTTP requests

MySQL operations

nvidia-smi

SMTP

SMS

OAuth network requests
```

Never wait indefinitely.

Failures should produce safe structured errors.

---

# 63. Security During Implementation

Every stage must verify:

```text
no secret committed

no token logged

no raw authorization header logged

no permissive CORS

no TLS verification bypass

no public MySQL

no shell execution from telemetry
```

---

# 64. Database Migration Rule

Every schema change requires:

```text
Alembic migration
```

Do not:

```text
manually modify production tables

delete old migrations

reset production database

drop tables to simplify development
```

Migration compatibility must be reviewed before deployment.

---

# 65. Test Evidence

At each stage report:

```text
tests executed

tests passed

tests failed

tests skipped

reason for skips
```

Never claim:

```text
tested
```

when the required environment was unavailable.

Examples:

```text
GPU test skipped:
no NVIDIA GPU available

Google integration skipped:
no approved OAuth credentials

SMS production test skipped:
provider not configured
```

These are acceptable if explicitly recorded.

---

# 66. Stage Completion Report

At every major implementation boundary, Codex should report:

```text
Stage:

Files changed:

Migrations added:

Commands executed:

Tests passed:

Tests failed:

Tests skipped:

Security impact:

Known limitations:

Recommended next stage:
```

This gives us a clean review point without forcing unnecessary approval after every tiny file.

---

# 67. Critical Acceptance Scenario

Before V1 is considered operational, demonstrate:

```text
1. Device enrolled.

2. Agent starts.

3. Heartbeat accepted.

4. CPU/RAM/disk visible.

5. GPU visible.

6. Device ONLINE.

7. Agent stopped.

8. Device SUSPECT.

9. Device OFFLINE.

10. One incident created.

11. One OFFLINE email generated.

12. Agent restarted.

13. Heartbeat accepted.

14. Device ONLINE.

15. Incident closed.

16. One RECOVERED email generated.

17. Dashboard reflects recovery.
```

This is the primary end-to-end proof.

---

# 68. Secondary Acceptance Scenario

Demonstrate:

```text
nvidia-smi fails
      ↓
system heartbeat still succeeds
      ↓
device remains reachable
      ↓
GPU state becomes non-OK
      ↓
confirmation threshold reached
      ↓
GPU incident opens
```

Then:

```text
GPU telemetry becomes healthy
      ↓
two fresh OK samples
      ↓
GPU incident closes
```

---

# 69. Restart Acceptance

Verify persistence across:

```text
API restart

worker restart

MySQL restart

central VM restart

edge device reboot
```

After restart:

```text
identity remains

history remains

credentials remain valid

agent resumes

worker resumes

dashboard resumes
```

---

# 70. Production Release Decision

Passing implementation stages does not automatically mean production deployment is safe.

Before actual production rollout, review:

```text
test evidence

failure tests

backup/restore

security configuration

DNS/TLS

recipient configuration

known limitations
```

Production rollout remains an explicit operational decision.

---

# 71. Deferred Beyond V1

Explicitly deferred:

```text
remote reboot

remote shell

remote command execution

service restart

driver repair

automatic remediation

self-healing

policy engine

advanced administration

multi-region deployment

high availability cluster
```

These require a separate security and operations design.

---

# 72. V1 Definition of Done

SkyBeat V1 is complete when:

```text
Linux/GPU agents
      ↓
authenticated HTTPS
      ↓
FastAPI
      ↓
MySQL
      ↓
server-side health engine
      ↓
incidents
      ↓
email/SMS abstraction
      ↓
Google-protected dashboard
```

works reliably for the intended fleet.

Operationally:

* devices are grouped by project
* device identity is stable
* telemetry is persisted
* availability is server-controlled
* duplicate heartbeats are safe
* GPU failures do not block host monitoring
* outages are deduplicated
* recoveries close the correct incident
* notifications are durable
* dashboard telemetry freshness is clear
* authentication and authorization are enforced
* services recover after restart
* backups can be restored
* no V1 feature performs remote device actions

The V1 architecture ends at:

```text
OBSERVE
   ↓
DETECT
   ↓
RECORD
   ↓
NOTIFY
   ↓
DISPLAY
```

It does not cross into:

```text
CONTROL
   ↓
REPAIR
   ↓
SELF-HEAL
```
