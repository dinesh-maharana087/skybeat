# AGENTS.md

## Project Overview

This repository contains the standalone SkyBeat V1 production-oriented Linux/GPU device monitoring and alerting platform.

SkyBeat V1 consists of:

* a central monitoring server deployed on Ubuntu
* lightweight Python monitoring agents installed on Linux/GPU devices
* MySQL 8.x persistent storage
* a separate health/notification worker
* a web dashboard for administrators
* Google OIDC authentication with explicit authorization
* email notification delivery
* a replaceable SMS notification interface
* Caddy for production HTTPS

The primary purpose of V1 is to reliably:

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

device and GPU health.

SkyBeat V1 does NOT perform remote administration, repair, or self-healing.

This project is standalone and is NOT part of Canopus.

---

# 1. Authoritative Documentation

Before implementing functionality, read the relevant approved specifications under `docs/`.

Authoritative documents:

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

This file controls Codex working behavior.

`docs/IMPLEMENTATION_PLAN.md` controls implementation sequencing.

The specifications define system behavior.

Do not silently override an approved specification.

If two approved documents materially conflict, stop and report the conflict rather than choosing one arbitrarily.

---

# 2. Current Implementation Authorization

Stage 00 documentation is complete.

The approved V1 implementation roadmap consists of:

```text
Stage 01
Foundation + Database + Device Identity

Stage 02
Heartbeat API + Agent

Stage 03
Availability + Incidents + Email

Stage 04
Dashboard + Google Authentication

Stage 05
GPU Incidents + SMS Boundary

Stage 06
Deployment + Production Hardening
```

These stages are the approved V1 implementation scope.

Once the user explicitly authorizes implementation to begin, Codex may proceed through these approved V1 stages sequentially without requiring a new approval after every stage.

However, Codex must still:

1. complete the current stage
2. run its required verification
3. update implementation status
4. record unresolved issues
5. continue only when no stop condition applies

Do not expand beyond the approved V1 scope.

Production rollout or destructive production operations still require explicit human approval.

---

# 3. Session Continuity and Token-Exhaustion Recovery

Codex sessions may end because of:

* token exhaustion
* context limits
* editor restart
* network interruption
* process interruption
* manual session restart

Implementation progress must therefore be recoverable from repository state.

Codex must maintain:

```text
docs/IMPLEMENTATION_STATUS.md
```

during implementation.

This file is the persistent implementation checkpoint.

It must be updated:

```text
after each meaningful completed milestone

before intentionally ending a long session

at every stage completion

after discovering a blocker that prevents safe continuation
```

Do not update the checkpoint to claim work that has not been verified.

---

# 4. IMPLEMENTATION_STATUS.md Format

If implementation has begun and the file does not exist, create:

```markdown
# SkyBeat V1 Implementation Status

Last updated:
Current stage:
Current milestone:
Status:

## Completed

- ...

## In Progress

- ...

## Verification Completed

- ...

## Verification Pending

- ...

## Files Changed

- ...

## Migrations Applied/Tested

- ...

## Known Issues

- ...

## Security Notes

- ...

## Environment Limitations

- ...

## Next Action

- ...

## Resume Command / Guidance

Read AGENTS.md, docs/IMPLEMENTATION_PLAN.md, this file, and inspect the current Git diff before continuing.
```

Keep it concise and factual.

Do not turn it into a development diary.

---

# 5. Resume Procedure

At the beginning of a new Codex session, if implementation has already started:

```text
1. Read AGENTS.md.

2. Read docs/IMPLEMENTATION_STATUS.md.

3. Read the current stage in docs/IMPLEMENTATION_PLAN.md.

4. Read the specifications relevant to that stage.

5. Inspect git status.

6. Inspect git diff.

7. Inspect existing migrations.

8. Inspect the files listed as changed/in-progress.

9. Run the smallest useful verification needed to confirm repository state.

10. Resume from the first unverified milestone.
```

Never assume the previous session completed work merely because files exist.

Never restart the entire implementation merely because the previous Codex conversation is unavailable.

Repository state is authoritative.

---

# 6. Uncertain Resume State

If `IMPLEMENTATION_STATUS.md` says:

```text
implemented
```

but tests were not recorded:

```text
treat the work as unverified
```

Run the relevant tests before continuing.

If the status file disagrees with repository contents:

```text
repository + tests
```

take precedence over the status description.

Correct the status file after determining the actual state.

If the previous session ended during a migration or other potentially unsafe operation, inspect the state before rerunning anything.

Do not blindly replay commands.

---

# 7. Core Engineering Principles

Prioritize:

1. Security
2. Data integrity
3. Reliability
4. Simplicity
5. Observability
6. Maintainability
7. Recoverability
8. Testability

Prefer boring, well-understood production technology over unnecessary complexity.

Do not introduce additional infrastructure unless there is a demonstrated requirement.

Do not silently make major architectural changes.

---

# 8. Scope Boundaries

V1 MAY:

* collect telemetry
* send heartbeats
* determine device availability
* determine GPU health
* store telemetry/history
* display device status
* create incidents/events
* send email notifications
* provide a replaceable SMS provider interface
* send SMS when an approved real provider is configured
* record recovery events
* authenticate administrators
* organize devices by project

V1 MUST NOT:

* execute arbitrary commands on devices
* provide remote shell access
* remotely reboot devices
* restart remote services
* modify operating-system configuration
* modify GPU drivers
* automatically repair systems
* implement self-healing
* execute user-supplied commands
* expose unrestricted administrative APIs

Do not implement these features even if convenient.

---

# 9. Approved Architecture

High-level architecture:

```text
Linux / GPU Agents
        │
        │ HTTPS
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
   └── Jinja2 Dashboard
```

Architectural style:

```text
modular monolith
```

API and worker use the same Python application/package but run as separate processes.

Do not introduce:

```text
Redis
Celery
RabbitMQ
Kafka
Kubernetes
microservices
time-series databases
React
Vue
```

without an approved architecture change.

---

# 10. Repository Structure

Target structure is approximately:

```text
server/
├── app/
├── migrations/
└── tests/

agent/
├── src/
└── tests/

web/
├── templates/
└── static/

deployment/
├── docker/
├── caddy/
└── systemd/

docs/

tests/
├── contracts/
├── integration/
├── failure/
└── load/

scripts/

.env.example
docker-compose.yml
README.md
AGENTS.md
```

This may evolve when justified.

Major architectural changes require review.

---

# 11. Database

The authoritative persistent datastore is:

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

Application timestamps are handled as:

```text
UTC
```

Use:

```text
SQLAlchemy 2
Alembic
```

Do not introduce PostgreSQL.

Do not use SQLite as production storage.

SQLite tests may not be used as proof of MySQL-specific transactional/concurrency correctness.

---

# 12. MySQL Concurrency

Important concurrency behavior must be tested against real MySQL 8.x/InnoDB.

Where required, use transactional row locking such as:

```sql
SELECT ...
FROM devices
WHERE id = ?
FOR UPDATE;
```

MySQL 8.x `SKIP LOCKED` may be used where justified for worker job claiming.

Verify behavior through integration tests.

Do not copy PostgreSQL-specific SQL or operational assumptions.

---

# 13. Database Migrations

Every schema change requires an Alembic migration.

Never:

* modify production schema manually without a migration
* delete old migrations to simplify development
* reset production databases
* drop tables to fix migration mistakes
* recreate production data casually

Migration filenames may use descriptive suffixes.

Actual revision IDs are generated by Alembic.

---

# 14. Device Organization

Hierarchy:

```text
Project
└── Device
```

A device has separate:

```text
UUID
Device Name
Hostname
Project
Credential
```

Device UUID is the immutable technical identity.

Device Name is a human-friendly server-controlled label.

Hostname is reported by Linux and may change.

Project is organizational metadata.

Renaming/moving a device must not alter:

* UUID
* credential
* telemetry history
* incident history

---

# 15. Device Authentication

Every device has its own credential.

Never use one fleet-wide secret.

Credential format:

```text
sb1.<credential_id>.<secret>
```

Secret generation must use cryptographically secure randomness.

The server stores only an appropriate secure representation.

Credentials must support:

* revocation
* rotation
* expiration where configured
* device binding

Never log raw credentials.

Never commit them.

---

# 16. Edge Agent

The agent must remain lightweight.

Primary target:

```text
Linux GPU servers
```

Initial supported environments are defined in `AGENT_SPEC.md`.

The agent runs under:

```text
systemd
```

The agent must:

* start automatically after boot
* restart after unexpected failure
* collect system telemetry
* collect NVIDIA GPU telemetry
* send periodic heartbeats
* tolerate temporary network failures
* use bounded timeouts
* use bounded retries
* fail safely
* produce useful non-sensitive logs

The agent must not expose an inbound listener.

---

# 17. Agent Configuration

Preferred:

```text
/etc/skybeat-agent/agent.env
```

Required:

```text
SKYBEAT_SERVER_URL

SKYBEAT_DEVICE_ID

SKYBEAT_DEVICE_TOKEN
```

The agent does not require project information.

Project assignment is server-controlled.

---

# 18. Heartbeat

Default interval:

```text
30 seconds
```

with small jitter.

Every new telemetry snapshot receives a unique:

```text
heartbeat_id
```

Retries of the same snapshot reuse:

```text
same heartbeat_id
same payload
```

The server is authoritative for device availability.

Never depend on an agent sending:

```text
"I am offline"
```

---

# 19. Heartbeat Idempotency

Logical duplicate key:

```text
device_id + heartbeat_id
```

Duplicate retention:

```text
at least 24 hours
```

Identical retry:

```text
return original acknowledgement
```

but do NOT:

* refresh liveness
* update latest telemetry
* advance GPU confirmation
* create recovery
* create duplicate events

Same heartbeat ID with different payload:

```text
409 conflict
```

---

# 20. Availability

Server receipt time is authoritative.

Default states:

```text
ONLINE
SUSPECT
OFFLINE
```

Thresholds:

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
approximately every 5 sec
```

Do not mark a device OFFLINE because of one missed heartbeat.

---

# 21. Never-Seen Devices

A newly enrolled device with no accepted heartbeat should normally appear as:

```text
AWAITING_FIRST_HEARTBEAT
```

unless an explicitly configured enrollment policy has already created an OFFLINE incident.

First-ever normal contact is not automatically a recovery event.

---

# 22. Late Heartbeats

A heartbeat arriving after the OFFLINE threshold must not erase an outage merely because the worker has not swept yet.

Heartbeat ingestion and health sweep must reconcile transitions transactionally.

Example:

```text
last seen:
12:00:00

offline threshold:
12:03:00

new heartbeat:
12:03:10
```

Logical history must preserve:

```text
OFFLINE
   ↓
RECOVERED
```

when policy requires that outage to exist.

---

# 23. System Telemetry

Initial host telemetry:

```text
device UUID

hostname

IP addresses

OS

kernel/architecture where defined

agent version

uptime

CPU

memory

filesystems
```

Do not collect unrelated user/process/application data.

---

# 24. GPU Monitoring

Use controlled execution of:

```text
nvidia-smi
```

with:

```text
shell=False
fixed arguments
read-only query
bounded output
timeout
```

Never assume `nvidia-smi` succeeds.

Handle:

* command missing
* permission denied
* timeout
* stuck collector
* non-zero exit
* malformed output
* oversized output
* driver failure
* no GPU
* multiple GPUs

---

# 25. GPU States

Supported aggregate states:

```text
OK

GPU_MISSING

NVIDIA_SMI_FAILED

DRIVER_ERROR

UNKNOWN
```

GPU monitoring disabled is displayed as:

```text
NOT MONITORED
```

not `OK`.

GPU availability is independent of device availability.

Example:

```text
Device:
ONLINE

GPU:
DRIVER_ERROR
```

is valid.

---

# 26. GPU Identity

Prefer:

```text
GPU UUID
```

over:

```text
GPU index
```

for persistent identity.

Do not assume a device contains only one GPU.

Expected GPU inventory is server-controlled.

The agent must not automatically redefine the expected inventory when a GPU disappears.

---

# 27. GPU Confirmation

GPU degradation notifications should require:

```text
2 distinct fresh non-OK observations
```

GPU recovery should require:

```text
2 distinct fresh OK observations
```

Duplicate heartbeat retries do not count as new observations.

Availability outage/recovery takes operational precedence while the device is OFFLINE.

---

# 28. Incidents

One continuing availability outage produces:

```text
one active incident
```

and:

```text
one DEVICE_OFFLINE event
```

Repeated sweeps do not create duplicates.

Recovery:

```text
OFFLINE
   ↓
ONLINE
```

closes the incident and creates:

```text
one DEVICE_RECOVERED event
```

A later new outage creates a new incident.

---

# 29. Alert Generation vs Delivery

These are separate concerns.

Conceptually:

```text
Incident
   ↓
Alert Event
   ↓
Notification Delivery
   ↓
Notification Attempt
```

An alert existing does NOT mean notification delivery succeeded.

Provider calls must not occur inside the heartbeat transaction.

---

# 30. Notification Providers

Provider abstraction:

```text
NotificationProvider
├── EmailProvider
└── SMSProvider
```

Email:

```text
SMTP
```

SMS must remain replaceable.

Do not bind incident logic directly to a particular SMS vendor.

---

# 31. Notification Delivery State

Use durable states aligned with `ALERTING.md`.

Conceptually:

```text
PENDING

IN_PROGRESS

RETRY_WAIT

SUCCEEDED

FAILED

CANCELLED
```

If implementation uses slightly different persisted names, they must match the approved alerting/API contract consistently.

Persist attempt history.

One provider failure must not block another provider.

---

# 32. Notification Retries

Initial maximum:

```text
5 attempts
```

Provider attempt timeout:

```text
approximately 15 seconds
```

Notification expiry:

```text
approximately 24 hours
```

Use bounded exponential retry with jitter.

Classify failures as:

```text
accepted

transient

permanent

uncertain
```

where supported by the provider interface.

Never claim exactly-once external delivery.

---

# 33. Stale Outage Notification Cancellation

If recovery occurs before an outage notification is delivered:

```text
PENDING
```

or:

```text
RETRY_WAIT
```

outage deliveries should be cancelled/superseded.

Do not intentionally deliver a stale outage after recovery.

Already accepted external delivery cannot necessarily be recalled.

Recovery notification behavior follows `ALERTING.md`.

---

# 34. Dashboard Authentication

Use Google OIDC.

Authentication and authorization are separate.

A valid Google account must NOT automatically receive access.

Authorization must use:

```text
explicit email allowlist
```

and optionally an approved hosted-domain policy.

Empty authorization policy:

```text
DENY
```

---

# 35. Browser Sessions

Use application-owned opaque sessions.

Persist only an appropriate secure digest.

Cookies must be:

```text
Secure
HttpOnly
SameSite=Lax
```

Do not place Google tokens or device credentials in browser storage.

---

# 36. API Security

All external input must be validated.

Apply:

* authentication
* authorization
* request size limits
* bounded timeouts
* safe rate limits
* structured errors
* output encoding

Never expose production exception traces.

Never use permissive production CORS without an approved reason.

Dashboard and API are same-origin in V1.

---

# 37. Secret Handling

Never log:

* passwords
* device tokens
* authorization headers
* Google tokens
* Google client secret
* session cookies
* SMTP passwords
* SMS credentials
* MySQL passwords
* private keys

Never commit them.

Use environment/configuration files with restrictive permissions.

---

# 38. Logging

Use structured logging where practical.

Useful fields include:

```text
timestamp
level
component
request ID
device UUID
event type
error category
```

Do not log full routine heartbeat payloads by default.

Do not log raw `nvidia-smi` output unless explicitly sanitized for a controlled diagnostic situation.

Production logs must rotate.

---

# 39. Error Handling

Do not silently swallow exceptions.

Expected failures must be handled explicitly.

Unexpected failures should:

1. be logged safely
2. preserve useful troubleshooting context
3. avoid exposing sensitive information
4. fail safely

Broad exception handlers belong only at appropriate system boundaries.

---

# 40. Configuration

Runtime configuration comes from:

```text
environment variables
```

or approved protected configuration files.

Provide:

```text
.env.example
```

with variable names and safe placeholders.

Never include real production secrets.

---

# 41. Docker

Central deployment uses Docker Compose.

Services:

```text
caddy
api
worker
mysql
```

API and worker should normally use the same application image with different entry points.

Only Caddy exposes application traffic publicly.

Do not publicly expose:

```text
3306
8000
```

MySQL must remain on the internal network.

---

# 42. Caddy

Caddy provides:

* HTTPS
* certificate renewal
* HTTP → HTTPS redirect
* reverse proxy
* host validation
* basic request protection

Do not replace Caddy with Nginx unless the architecture is explicitly revised.

---

# 43. Edge Deployment

Agents run directly on Linux rather than in Docker.

Provide:

```text
systemd service
```

Preferred paths:

```text
/opt/skybeat

/etc/skybeat-agent/agent.env

/etc/systemd/system/skybeat-agent.service
```

Use a dedicated service account where practical.

---

# 44. Testing

Every important production behavior requires tests.

At minimum cover:

* heartbeat validation
* device authentication
* credential revocation
* heartbeat storage
* heartbeat duplicate behavior
* concurrent duplicate heartbeat
* availability boundaries
* late heartbeat
* offline detection
* recovery
* incident deduplication
* notification retry
* stale notification cancellation
* malformed agent payload
* `nvidia-smi` failure
* `nvidia-smi` timeout
* no GPU
* multiple GPUs
* database failure
* worker restart
* API restart
* authorization failure

Do not consider a feature complete merely because its happy path works.

---

# 45. Real MySQL Tests

MySQL-specific behavior must be tested using:

```text
MySQL 8.x / InnoDB
```

This includes:

* row locking
* concurrent heartbeat/sweep
* duplicate incident prevention
* worker claiming
* rollback
* lock timeout
* reconnect behavior

Do not substitute SQLite for these tests.

---

# 46. Failure Testing

Production acceptance should exercise:

* agent killed
* monitored device reboot
* network disconnected
* server unreachable
* API restart
* worker restart
* MySQL restart
* monitoring VM restart
* `nvidia-smi` timeout
* NVIDIA driver failure
* GPU disappearance
* SMTP unavailable
* SMS unavailable
* backup restore

Expected behavior must be recorded.

---

# 47. Backward Compatibility

Server and agent may be upgraded independently.

Heartbeat includes:

```text
schema_version
agent_version
```

Do not casually introduce breaking heartbeat changes.

Breaking contract changes require a new schema version and compatibility review.

---

# 48. Code Quality

Prefer:

* small modules
* explicit interfaces
* typed Python
* meaningful names
* pure/testable business logic
* separation of transport/persistence/business logic
* dependency injection where useful

Avoid:

* giant modules
* hidden global state
* premature abstraction
* microservices
* duplicated logic
* magic numbers
* hardcoded credentials
* hardcoded production URLs

---

# 49. No Premature Future Architecture

Do not build:

```text
command engine

workflow engine

remote executor

repair engine

self-healing engine

plugin marketplace

distributed event bus

multi-region system
```

for V1.

Future possibilities are not implementation requirements.

---

# 50. Documentation

When implementation materially changes documented behavior, update the relevant documentation during the same stage.

Do not silently let code and documentation diverge.

If a documented design must change for a valid technical reason, explain the reason before making a major architectural/security change.

---

# 51. Production Safety

A component is not production-ready merely because it runs.

Production readiness requires appropriate:

* testing
* authentication
* authorization
* error handling
* timeouts
* retries
* logging
* persistence
* backups
* restore procedure
* configuration management
* deployment documentation
* failure testing

Explicitly report unresolved production concerns.

---

# 52. Codex Working Procedure

Before modifying code:

```text
1. Read AGENTS.md.

2. Read IMPLEMENTATION_STATUS.md if it exists.

3. Determine current stage.

4. Read relevant specifications.

5. Inspect existing implementation.

6. Inspect git status/diff.

7. Identify dependencies and migrations affected.
```

Then implement the smallest coherent milestone.

---

# 53. Codex Verification Procedure

After a meaningful milestone:

```text
1. Run targeted tests.

2. Run affected regression tests.

3. Run configured lint/format checks.

4. Run type checks where configured.

5. Inspect errors/warnings.

6. Inspect git diff.

7. Verify acceptance criteria.

8. Update IMPLEMENTATION_STATUS.md.
```

Do not claim a check passed unless it actually ran successfully.

---

# 54. Stage Completion Report

At stage completion record:

```text
Stage:

Status:

Files changed:

Migrations:

Tests executed:

Passed:

Failed:

Skipped:

Security implications:

Known limitations:

Next stage:
```

Update `docs/IMPLEMENTATION_STATUS.md` before continuing.

---

# 55. Automatic Stage Continuation

After implementation has been explicitly authorized, completing an approved V1 stage does NOT by itself require Codex to stop.

Codex may continue to the next approved stage when:

```text
current stage acceptance criteria are satisfied

relevant tests pass

no unresolved security blocker exists

no destructive production operation is required

no architecture conflict exists

the next stage is already part of the approved V1 roadmap
```

Before continuing:

```text
update docs/IMPLEMENTATION_STATUS.md
```

Then proceed to the next stage.

This rule exists so long-running implementation can continue efficiently without requiring repeated approval for already-approved V1 work.

---

# 56. Mandatory Stop Conditions

STOP and request human review if:

* a major architecture change is required
* approved specifications materially conflict
* a security-sensitive assumption cannot be resolved safely
* production credentials are required but unavailable
* an operation would modify existing production infrastructure unexpectedly
* destructive database work appears necessary
* persistent production data could be lost
* device credentials need unplanned fleet-wide rotation
* implementation would add remote-control capability
* an external provider requires a policy/product decision
* test evidence reveals the approved design is unsafe
* scope must expand beyond V1

Do not guess through these conditions.

---

# 57. Non-Blocking External Dependencies

The following should not unnecessarily stop unrelated implementation:

```text
Google production OAuth credentials unavailable

SMS provider not yet selected

SMS credentials unavailable

production SMTP credentials unavailable

production DNS unavailable

production TLS hostname unavailable

representative NVIDIA hardware temporarily unavailable
```

When possible:

```text
implement the approved interface

use safe test/fake infrastructure

run all possible tests

record the missing external prerequisite

continue with unrelated approved work
```

Do not falsely claim the unavailable external integration was verified.

---

# 58. Production Operations Require Separate Approval

Implementation authorization does NOT automatically authorize:

* production deployment
* destructive restore
* production database reset
* production credential rotation
* firewall changes on an existing production host
* modifying existing production agents
* sending test notifications to real customers/operators without approval

Build and isolated testing may continue.

Actual production-affecting actions require explicit approval.

---

# 59. Destructive Operations

Do not perform destructive operations without explicit approval.

Examples:

* deleting persistent data
* dropping tables
* deleting migrations
* removing Docker volumes
* resetting databases
* overwriting production configuration
* rotating live credentials
* removing deployed agents

Prefer reversible changes.

---

# 60. Git Discipline

Keep changes logically scoped.

Recommended commit naming if commits are requested:

```text
stage-01: establish foundation and device identity

stage-02: implement heartbeat and agent

stage-03: implement availability and email alerts

stage-04: implement dashboard authentication

stage-05: implement gpu incidents and sms boundary

stage-06: harden deployment
```

Do not commit:

```text
.env

agent.env

credentials

private keys

production database dumps

OAuth secrets

SMTP passwords

SMS credentials
```

Do not commit automatically unless the user has asked Codex to make commits or the repository workflow explicitly requires it.

---

# 61. Definition of Done — Milestone

A milestone is complete when:

* scoped implementation exists
* targeted tests pass
* known failure cases are considered
* secrets are absent
* documentation/status is updated where necessary

A milestone does not need to satisfy the entire stage.

This allows safe checkpoints before token/session exhaustion.

---

# 62. Definition of Done — Stage

A stage is complete when:

* implementation matches approved requirements
* migrations are present where required
* automated tests pass
* relevant negative/failure cases pass
* MySQL-specific behavior has real MySQL verification where required
* documentation is consistent
* no secrets are committed
* security implications are reviewed
* acceptance criteria are verified
* known limitations are recorded
* `IMPLEMENTATION_STATUS.md` is updated

Passing tests alone does not automatically make the stage production-ready.

---

# 63. Day 1 Priority

Protect this vertical path first:

```text
Project
   ↓
Device enrollment
   ↓
Agent
   ↓
HTTPS heartbeat
   ↓
FastAPI
   ↓
MySQL
   ↓
latest telemetry
```

Telemetry:

```text
CPU
RAM
Disk
Uptime
GPU
```

Do not spend Day 1 polishing dashboard appearance.

---

# 64. Day 2 Priority

Protect:

```text
Heartbeat stops
   ↓
SUSPECT
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
ONLINE
   ↓
Incident closes
   ↓
RECOVERED
   ↓
Email
```

Then secure dashboard access.

---

# 65. Day 3 Priority

Complete:

```text
GPU incident confirmation

SMS provider boundary

Docker Compose

Caddy

systemd

backup

restore verification

failure testing

security hardening
```

Do not sacrifice core correctness to finish optional polish.

---

# 66. Priority Under Time Pressure

P0:

```text
heartbeat

agent

CPU/RAM/disk/GPU telemetry

availability

incident correctness

OFFLINE email

RECOVERED email

authentication

HTTPS

MySQL persistence

backup
```

P1:

```text
GPU incident alerts

real SMS adapter

dashboard detail

additional operational hardening
```

P2:

```text
advanced visualization

WebSockets

Prometheus/Grafana

distributed infrastructure

advanced routing
```

Security, identity, durable commits, and outage correctness are never downgraded to save time.

---

# 67. Dependency Policy

Before adding a dependency:

```text
ask whether the standard library or an existing dependency is sufficient
```

Dependencies must be:

* maintained
* appropriate for production
* pinned/constrained
* necessary

Do not add large frameworks for small functionality.

---

# 68. Command Execution Safety

Do not construct shell commands using untrusted telemetry.

For `nvidia-smi`:

```text
shell=False
```

Use fixed argument arrays.

Do not execute:

```text
device-supplied commands

dashboard-supplied commands

telemetry strings

shell fragments
```

---

# 69. External Operation Bounds

Every external operation must have bounded execution.

Includes:

```text
HTTP

MySQL

OAuth/JWKS

SMTP

SMS

nvidia-smi
```

Never wait indefinitely.

---

# 70. Dashboard Scope

V1 contains one main Device Status experience.

Do not build:

* large analytics suite
* complex SPA
* control panel for remote operations
* user-management product
* arbitrary telemetry query builder

Use:

```text
Jinja2
CSS
small JavaScript
```

unless an approved design change says otherwise.

---

# 71. Deployment Scope

Central deployment:

```text
Ubuntu 24.04 LTS
   │
Docker Compose
   ├── Caddy
   ├── API
   ├── Worker
   └── MySQL
```

Agent:

```text
Linux
   │
systemd
   │
skybeat-agent
```

No Kubernetes.

---

# 72. Backup

Initial production design requires:

```text
daily MySQL backup

off-host copy

approximately 30-day retention
```

A backup is not considered proven until restore has been tested.

Do not claim production recovery readiness without restore evidence.

---

# 73. Central Monitoring Blind Spot

SkyBeat cannot reliably report complete failure of its own central VM.

Production deployment should eventually use an independent external uptime/dead-man mechanism.

This does not require adding another SkyBeat service to V1.

---

# 74. Environment-Limited Tests

If required infrastructure is unavailable, report it accurately.

Examples:

```text
SKIPPED:
No NVIDIA GPU available.

SKIPPED:
No approved Google OAuth credentials.

SKIPPED:
No production SMS provider configured.
```

Do not convert a skipped integration into a success claim.

Continue with unrelated approved work where safe.

---

# 75. Resume Safety After Interrupted Tool Execution

If a session ends while a command may have been executing:

Do not immediately rerun it.

First inspect:

```text
process state

git state

filesystem state

migration state

database state when relevant
```

Examples include:

```text
Alembic migration

package installation

Docker Compose changes

backup/restore

long-running tests
```

Determine whether the previous operation:

```text
completed

failed

partially completed

is still running
```

before deciding what to do.

---

# 76. Checkpoint Granularity

During long implementation sessions, create a status checkpoint after completing a coherent milestone such as:

```text
database foundation complete

device enrollment complete

heartbeat ingestion complete

agent system collector complete

GPU collector complete

availability state machine complete

email delivery complete

dashboard authentication complete

Compose deployment complete
```

This prevents loss of reasoning/progress when the Codex context expires.

Do not checkpoint after every trivial edit.

---

# 77. Implementation Status Is Not Authority

`IMPLEMENTATION_STATUS.md` records progress.

It does not override:

```text
AGENTS.md

approved specifications

actual repository state

test results
```

If the status file is wrong, correct it.

---

# 78. Architecture Change Procedure

If implementation reveals that the approved architecture is unsuitable:

```text
STOP
```

Report:

* problem
* evidence
* why current design is insufficient
* alternatives
* advantages/disadvantages
* migration impact
* security impact
* recommendation

Do not make the major change first and explain it afterward.

---

# 79. Final V1 Acceptance

Before declaring V1 complete, demonstrate:

```text
device enrolled
      ↓
agent running
      ↓
heartbeat accepted
      ↓
telemetry persisted
      ↓
device ONLINE
      ↓
agent stopped
      ↓
SUSPECT
      ↓
OFFLINE
      ↓
one incident
      ↓
one outage notification
      ↓
agent restarted
      ↓
ONLINE
      ↓
incident closed
      ↓
one recovery notification
      ↓
dashboard reflects recovery
```

Also verify GPU collector failure does not stop system heartbeat.

---

# 80. Final Instruction Priority

When instructions compete, prioritize:

1. Security
2. Data integrity
3. Reliability
4. Approved specifications
5. Current implementation stage
6. Maintainability
7. Performance optimization
8. Convenience

Do not sacrifice security or correctness merely to finish faster.

---

# 81. Final Rule

Build the smallest system that correctly satisfies the approved V1.

Do not build future SkyBeat.

Do not build Canopus.

Do not build a remote administration platform.

Build:

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

Make it reliable, secure, testable, recoverable, and easy for the next Codex session to continue.
