# V1 Requirements and Acceptance Criteria

Status: proposed for architecture review, 2026-09-21.

Stage 00 produces documentation only.

Initial production sizing target: up to 100 monitored devices on one Ubuntu VM.

All operational thresholds and implementation stages remain configurable and subject to validation during production testing.

---

# 1. Intended Outcome

The system is a standalone production-oriented device and GPU monitoring and alerting platform.

Administrators must be able to:

* organize devices into projects
* assign human-readable names to devices
* identify devices that have stopped contacting the monitoring server
* observe current system telemetry
* observe NVIDIA GPU telemetry and GPU health
* determine when telemetry is stale
* receive device outage notifications
* receive device recovery notifications
* inspect persistent outage and notification history

The platform has no dependency on Canopus.

The server cannot determine the exact cause of a missing heartbeat from absence alone.

A missing heartbeat may indicate:

* powered-off device
* operating-system failure
* network failure
* monitoring-agent failure
* routing/VPN failure
* other connectivity problems

Therefore, availability alerts describe loss of device/agent contact rather than claiming a specific root cause.

GPU health represents observed NVIDIA telemetry/driver accessibility and must not be presented as a comprehensive hardware diagnostic.

---

# 2. V1 Scope

Required V1 capabilities:

* FastAPI REST server
* MySQL 8.x
* SQLAlchemy
* Alembic database migrations
* Linux Python monitoring agent
* HTTPS production deployment
* systemd agent lifecycle
* project/device organization
* one main Device Status dashboard
* Google authentication
* explicit dashboard authorization
* device offline detection
* device recovery detection
* alert deduplication
* durable notification retries
* SMTP/email notifications
* replaceable SMS provider interface
* persistent device/event/notification history

GPU monitoring must support explicit health states and multiple GPUs.

GPU degradation/recovery notifications may be enabled after the basic device availability notification path is validated.

V1 does not require:

* temperature threshold alarms
* utilization threshold alarms
* metric graphs
* recurring outage reminders
* escalation policies
* multi-tenancy
* billing
* public administration API
* complex administration UI
* remote enrollment UI

---

# 3. Explicitly Excluded Capabilities

V1 MUST NOT provide:

* remote shell
* remote reboot
* arbitrary command execution
* user-supplied command execution
* remote OS configuration
* automatic repair
* self-healing
* unrestricted administrative APIs

The monitoring agent may execute predefined read-only local telemetry commands such as `nvidia-smi`.

Such subprocesses must have:

* fixed command structure
* bounded runtime
* bounded output
* explicit error handling

---

# 4. Project Organization

The platform must support projects as an organizational layer.

Conceptual relationship:

Project
-> Devices
-> Heartbeats / telemetry
-> GPUs
-> Events
-> Alerts

A project may contain zero or more devices.

A device belongs to one project in V1.

A device may later be reassigned to another project without:

* changing its immutable device UUID
* regenerating its identity unnecessarily
* losing telemetry history
* losing event history

Project assignment is organizational metadata and MUST NOT determine device authentication.

Each project must support at minimum:

* internal ID
* name
* optional description
* active/inactive state
* created timestamp
* updated timestamp

Project names should be human-readable.

---

# 5. Device Identity

Each monitored device must have:

* internal database ID
* immutable device UUID
* project assignment
* human-readable device name
* hostname
* IP information
* operating-system information
* agent version
* availability state
* last heartbeat timestamp
* first registered timestamp
* active/inactive state
* created timestamp
* updated timestamp

The human-readable device name is NOT an authentication identity.

The device UUID represents the stable device identity.

Every device must have independently revocable authentication credentials.

Fleet-wide shared agent credentials are prohibited.

---

# 6. Device Registration

Devices are operator-enrolled.

An edge agent MUST NOT be allowed to create arbitrary:

* projects
* device identities
* administrator accounts

Enrollment establishes:

* device UUID
* device credential
* project assignment
* human-readable device name

The server remains authoritative for project/device mapping.

Credentials must support:

* revocation
* rotation
* bounded overlap during rotation

Credentials must never be stored in source code or committed to Git.

---

# 7. Server Requirements

## SRV-01

The FastAPI service must provide:

* environment-based configuration
* structured logging
* controlled application startup
* graceful shutdown
* liveness endpoint
* readiness endpoint

Invalid configuration must fail safely.

Graceful shutdown must close database and network resources.

Health endpoints must expose no credentials or sensitive configuration.

## SRV-02

MySQL 8.x is the authoritative relational database.

All schema changes must use Alembic migrations.

Acceptance requires:

* empty database can migrate to current schema
* previous-stage schema can upgrade without unintended data loss
* schema mismatch prevents application readiness when unsafe
* migrations are reproducible

MySQL is the only relational database required by production.

SQLite must not be used as a substitute for MySQL-specific integration/concurrency testing.

---

# 8. Heartbeat Requirements

Agents should publish approximately every 30 seconds.

The interval must be configurable.

Heartbeat requests must:

* authenticate the device
* validate schema version
* validate payload size
* validate array/scalar limits
* reject incompatible versions
* reject malformed telemetry
* reject non-finite numeric values
* reject inappropriate unknown fields

The server must commit accepted heartbeat state before acknowledging success.

Database failure or commit failure must not produce a false successful acknowledgement.

Duplicate heartbeat submissions must not incorrectly refresh device liveness.

Heartbeat processing must be idempotent where required.

---

# 9. Agent Requirements

The monitoring agent is Linux-first and Python-based.

It must run as a systemd service.

The service must:

* start after boot
* automatically restart after unexpected failure
* handle SIGTERM cleanly
* use a dedicated configuration
* operate without root where practical
* avoid excessive privileges

Network or telemetry failures must never cause the monitoring loop to hang indefinitely.

Use:

* request deadlines
* bounded retries
* exponential backoff where appropriate
* bounded subprocess execution
* bounded memory/storage behavior

Do not maintain an unlimited local telemetry queue.

For V1, newer observations may supersede unsent older routine telemetry where appropriate.

---

# 10. System Telemetry

Collect at minimum:

## Identity

* device UUID
* hostname
* IP address(es)
* operating system
* agent version
* uptime

## CPU

* utilization percentage

## Memory

* total
* used
* available
* utilization percentage

## Storage

For relevant filesystems/devices:

* mount/device
* total
* used
* free
* utilization percentage

Missing measurements must be represented explicitly as unavailable/null.

Do not fabricate zero values for unavailable telemetry.

---

# 11. GPU Monitoring

The agent must support zero, one, or multiple NVIDIA GPUs.

Collect where available:

* GPU index
* GPU UUID
* model
* utilization
* temperature
* total GPU memory
* used GPU memory
* NVIDIA driver version

GPU health must support explicit states including:

* OK
* GPU_MISSING
* NVIDIA_SMI_FAILED
* DRIVER_ERROR
* UNKNOWN

`nvidia-smi` execution must have:

* timeout
* bounded captured output
* non-zero exit handling
* malformed-output handling

Tests must cover:

* command missing
* timeout
* non-zero exit
* malformed output
* driver communication failure
* zero GPUs
* one GPU
* multiple GPUs
* reordered GPU indices
* partially unavailable telemetry

GPU UUID should be preferred over GPU index for stable GPU identity where available.

The system should be capable of detecting when an expected GPU disappears.

An automatically observed lower GPU count must not silently redefine the expected baseline.

---

# 12. Availability State Machine

The central server is authoritative for device availability.

The agent must NOT be expected to send an "offline" message.

Initial proposed states:

ONLINE
SUSPECT
OFFLINE

Recovery is represented as a transition/event.

Initial timing:

Heartbeat age < 75 seconds:
ONLINE

Heartbeat age >= 75 seconds and < 180 seconds:
SUSPECT

Heartbeat age >= 180 seconds:
OFFLINE

A newly enrolled device that has never sent a heartbeat must have separate pending/never-seen semantics.

One missed heartbeat must not immediately create an outage.

All thresholds must be configurable.

---

# 13. Availability Events

The system must persist important state transitions.

At minimum:

* DEVICE_OFFLINE
* DEVICE_RECOVERED

First contact from a newly registered device is not a recovery.

An OFFLINE → ONLINE transition generates exactly one recovery event for the completed outage.

State/event changes must remain deterministic under concurrent heartbeat and offline-detection processing.

Tests must include:

* heartbeat arriving during an offline sweep
* duplicate sweep workers
* late heartbeat
* API restart
* database restart
* concurrent state updates

---

# 14. Alert Deduplication

A continuing outage must generate only one outage incident.

Example:

ONLINE
-> OFFLINE
-> create outage incident
-> send notifications

OFFLINE
-> OFFLINE
-> no duplicate incident

OFFLINE
-> ONLINE
-> create recovery event

ONLINE
-> OFFLINE
-> create new outage incident

Deduplication behavior requires automated tests.

---

# 15. Notification Architecture

Alert generation and notification delivery must be separate concerns.

Conceptual architecture:

Alert Engine
|
+-- Notification Provider
|
+-- Email Provider
|
+-- SMS Provider

Creating an alert does not mean delivery succeeded.

Delivery attempts must have persistent status.

Expected states may include:

* PENDING
* PROCESSING
* ACCEPTED
* FAILED
* CANCELLED

Exact naming may be refined by the architecture specification.

---

# 16. Email and SMS

V1 must support SMTP email delivery.

SMS must use a provider abstraction so the implementation can later use:

* Twilio
* Indian SMS provider
* another approved provider

without changing the alert engine.

One provider failing must not prevent another configured provider from being attempted.

Provider calls require:

* timeout
* bounded retry
* failure logging
* durable status

Notification failures must never roll back accepted heartbeat processing.

---

# 17. Stale Notification Handling

If a device recovers before a queued outage notification is delivered, the system must not misleadingly deliver an obsolete outage message without context.

Queued/retry notification jobs should support cancellation or stale-event handling.

Uncertain provider outcomes must be recorded honestly.

---

# 18. Google Authentication

Dashboard authentication uses Google OIDC/OAuth.

Authentication alone does not authorize dashboard access.

Authorization must use an explicit:

* email allowlist

and/or

* approved-domain allowlist

A valid Google account outside the configured authorization policy must be rejected.

Browser sessions must be protected and expire appropriately.

---

# 19. Device Status Dashboard

V1 contains one main Device Status page.

It must support project grouping and/or filtering.

Example:

Project A

Device-01    ONLINE
Device-02    ONLINE
Device-03    OFFLINE

Project B

Device-04    ONLINE
Device-05    SUSPECT

Each device should display at minimum:

* project
* device name
* availability
* last heartbeat
* hostname
* IP
* CPU utilization
* RAM utilization
* disk utilization
* GPU model
* GPU health
* GPU utilization
* GPU temperature
* GPU memory utilization
* uptime

Multiple GPUs and storage devices may be displayed through expandable device details.

Offline telemetry must be clearly identified as stale.

Unavailable values must not appear as zero.

Never-seen and monitoring-disabled devices must be distinguishable.

The dashboard should make unhealthy/offline devices visually identifiable without relying solely on color.

---

# 20. History

V1 must retain relevant:

* availability events
* GPU health events where enabled
* alerts
* notification delivery attempts

This does not require a second main dashboard page.

History may initially be exposed through:

* expandable device details
* paginated authenticated API

Delivery statuses must distinguish successful/accepted, pending, failed and cancelled outcomes.

---

# 21. Operational Requirements

Production deployment must provide:

* HTTPS entry point
* private MySQL networking
* persistent MySQL storage
* container/service health checks
* restart policies
* protected secrets
* log rotation
* backup procedure
* restore procedure

The database must not be publicly exposed.

Only required public ports should be reachable.

---

# 22. Reliability Targets

Initial proposed targets:

| Measure                        | Target                                                                                                     |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| Heartbeat                      | approximately every 30 seconds                                                                             |
| ONLINE                         | heartbeat age <75 seconds                                                                                  |
| SUSPECT                        | 75–<180 seconds                                                                                            |
| OFFLINE                        | >=180 seconds                                                                                              |
| Offline detection              | event committed approximately within 185 seconds under healthy server/database                             |
| First notification attempt     | within approximately 10 seconds of committed event when workers/providers are healthy and backlog is clear |
| Dashboard refresh              | approximately every 15 seconds while visible                                                               |
| GPU command deadline           | approximately 5 seconds                                                                                    |
| Agent HTTP total deadline      | approximately 10 seconds                                                                                   |
| Notification provider deadline | approximately 15 seconds                                                                                   |
| Agent memory target            | <=100 MiB RSS on declared reference system                                                                 |
| Agent idle CPU target          | <=1% of one CPU core on declared reference system                                                          |
| Soak test                      | 24 hours with 100 simulated devices                                                                        |

These are acceptance targets, not guarantees until measured.

---

# 23. MySQL Integration Testing

Integration tests must use the selected MySQL 8.x production major version.

Test real MySQL behavior for:

* migrations
* transactions
* unique constraints
* credential rotation
* concurrent heartbeat processing
* state transitions
* event creation
* notification job claims
* worker crashes
* lock contention
* database restart/recovery

SQLite is not an acceptable replacement for these tests.

---

# 24. Agent Testing

Tests must cover:

* scheduling
* retry/backoff
* network timeout
* system telemetry
* missing readings
* multiple filesystems
* GPU timeout
* missing nvidia-smi
* malformed nvidia-smi output
* multiple GPUs
* disappearing GPU
* process cleanup
* no zombie accumulation

Representative NVIDIA hardware must eventually be tested in addition to fixtures.

---

# 25. Security Testing

Test:

* missing device credential
* invalid credential
* revoked credential
* device identity mismatch
* oversized heartbeat
* malformed heartbeat
* rate limits
* safe error responses
* OAuth state/nonce validation
* issuer/audience validation
* unauthorized Google account
* expired browser session
* CSRF protections where applicable

Device-supplied text must be safely rendered by the dashboard.

---

# 26. Provider Testing

Email and SMS provider adapters must be tested for:

* success
* rejection
* timeout
* delayed response
* retry
* permanent failure
* unknown delivery outcome

Production credentials are used only during explicitly approved deployment tests.

---

# 27. Operational Failure Testing

Before production approval, test:

* killed agent
* agent crash/restart
* device reboot
* device network disconnection
* API restart
* MySQL restart
* monitoring VM restart
* hanging nvidia-smi
* unavailable NVIDIA driver
* missing GPU
* SMTP outage
* SMS provider outage
* backup restoration

Do not perform disruptive testing against production devices without explicit approval.

---

# 28. Production Release Gate

V1 must not be described as production-ready until:

* architecture is approved
* implementation stages are completed and verified
* MySQL migrations are tested
* real GPU inventory is tested
* HTTPS is enabled
* database is private
* device credentials are independently revocable
* Google authorization is deny-by-default
* rate limits are tested
* no secrets exist in Git/images/logs/error responses
* outage/recovery deduplication is tested
* heartbeat/offline race conditions are tested against MySQL
* SMTP controlled delivery succeeds
* SMS adapter is tested if live SMS is required
* resource/load/soak tests meet accepted targets
* logs and storage are bounded
* backup restoration is tested
* operational recovery procedure exists
* known limitations are documented

---

# 29. Initial Production Size

V1 should initially support:

100 monitored devices

with approximately:

30-second heartbeat interval

This produces roughly:

200 heartbeat requests per minute

under normal conditions.

The architecture should comfortably support this initial load without introducing unnecessary distributed infrastructure.

A message broker, Kubernetes cluster, microservice architecture or distributed database is not required for V1 unless testing demonstrates a genuine need.

---

# 30. Open Deployment Inputs

The following may be finalized before their respective deployment stages:

* production VM sizing
* public hostname/domain
* authorized Google emails/domains
* alert recipients
* SMTP provider
* SMS provider
* telemetry retention period
* event retention period
* backup retention
* RPO
* RTO
* final heartbeat/offline thresholds
* monitored GPU inventory
* responsible operator/on-call process

These inputs do not block architecture or initial implementation.

No production credentials should be assumed during development.
